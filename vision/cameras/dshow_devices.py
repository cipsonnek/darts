"""Video capture devices as DirectShow lists them, with name and device path.

OpenCV's DirectShow backend opens devices by their position in this same list, and Windows
renumbers that list whenever a camera is plugged in or drops off USB. The device path
(USB port and interface) stays the same for a camera on the same port, so a configured
camera can follow its physical device. Plain ctypes: no extra package to install."""

from __future__ import annotations

import ctypes
import logging
import platform
import threading
from ctypes import POINTER, byref, c_ulong, c_void_p, wintypes
from dataclasses import dataclass

log = logging.getLogger("vision.cameras")


@dataclass(frozen=True)
class VideoDevice:
    index: int
    name: str
    path: str

    @property
    def built_in(self) -> bool:
        """The laptop's own webcam (or its infrared face-login camera), never a board camera."""
        n = self.name.lower()
        return any(w in n for w in ("integrated", "built-in", "builtin", "wbudowan", "ir camera", "infrared",
                                    "facetime", "hello"))


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, s: str) -> "_GUID":
        h = s.strip("{}").replace("-", "")
        g = cls(int(h[0:8], 16), int(h[8:12], 16), int(h[12:16], 16))
        for i in range(8):
            g.Data4[i] = int(h[16 + 2 * i: 18 + 2 * i], 16)
        return g


class _VARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                ("r3", ctypes.c_ushort), ("val", c_void_p), ("pad", c_void_p)]


_CLSID_SystemDeviceEnum = "{62BE5D10-60EB-11d0-BD3B-00A0C911CE86}"
_IID_ICreateDevEnum = "{29840822-5B84-11D0-BD3B-00A0C911CE86}"
_CLSID_VideoInputDeviceCategory = "{860BB310-5D01-11d0-BD3B-00A0C911CE86}"
_IID_IPropertyBag = "{55272A00-42CB-11CE-8135-00AA004BB851}"
_VT_BSTR = 8
_lock = threading.Lock()


def _method(obj: c_void_p, index: int, *argtypes):
    """Method ``index`` of a COM object's vtable, bound to the object."""
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)
    fn = proto(vtbl[index])
    return lambda *a: fn(obj, *a)


def _release(obj: c_void_p) -> None:
    if obj:
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
        ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtbl[2])(obj)


def _read(bag: c_void_p, prop: str) -> str:
    var = _VARIANT()
    try:
        _method(bag, 3, wintypes.LPCWSTR, POINTER(_VARIANT), c_void_p)(prop, byref(var), None)
    except OSError:
        return ""
    try:
        return ctypes.wstring_at(var.val) if var.vt == _VT_BSTR and var.val else ""
    finally:
        ctypes.oledll.oleaut32.VariantClear(byref(var))


def list_video_devices() -> list[VideoDevice]:
    """Capture devices in DirectShow order (= OpenCV CAP_DSHOW index). Empty off Windows or
    when the list cannot be read."""
    if platform.system() != "Windows":
        return []
    with _lock:
        try:
            return _enumerate()
        except OSError as exc:
            log.warning("cannot list video devices", extra={"error": str(exc)})
            return []


def _enumerate() -> list[VideoDevice]:
    ole32 = ctypes.oledll.ole32
    hr = ctypes.windll.ole32.CoInitializeEx(None, 0)  # S_OK, S_FALSE or "already other mode": all usable
    devices: list[VideoDevice] = []
    dev_enum, enum_mon = c_void_p(), c_void_p()
    try:
        ole32.CoCreateInstance(byref(_GUID.parse(_CLSID_SystemDeviceEnum)), None, 1,  # CLSCTX_INPROC_SERVER
                               byref(_GUID.parse(_IID_ICreateDevEnum)), byref(dev_enum))
        res = _method(dev_enum, 3, POINTER(_GUID), POINTER(c_void_p), wintypes.DWORD)(
            byref(_GUID.parse(_CLSID_VideoInputDeviceCategory)), byref(enum_mon), 0)
        if res != 0 or not enum_mon:  # S_FALSE: no capture devices at all
            return []
        nxt = _method(enum_mon, 3, c_ulong, POINTER(c_void_p), POINTER(c_ulong))
        iid_bag = _GUID.parse(_IID_IPropertyBag)
        while True:
            mon, fetched = c_void_p(), c_ulong()
            if nxt(1, byref(mon), byref(fetched)) != 0 or not fetched.value:
                break
            bag = c_void_p()
            try:
                _method(mon, 9, c_void_p, c_void_p, POINTER(_GUID), POINTER(c_void_p))(
                    None, None, byref(iid_bag), byref(bag))
                devices.append(VideoDevice(len(devices), _read(bag, "FriendlyName"), _read(bag, "DevicePath")))
            except OSError:
                devices.append(VideoDevice(len(devices), "", ""))
            finally:
                _release(bag)
                _release(mon)
    finally:
        _release(enum_mon)
        _release(dev_enum)
        if hr in (0, 1):
            ctypes.windll.ole32.CoUninitialize()
    return devices


def index_for_path(path: str) -> int | None:
    """Where the device with this path is in today's numbering, or None (not connected)."""
    want = path.lower()
    for d in list_video_devices():
        if d.path.lower() == want:
            return d.index
    return None
