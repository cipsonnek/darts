"""USB cameras follow their physical device, and a laptop's own webcam is never taken."""

from __future__ import annotations

import yaml

import backend.services.vision_service as vs
from backend.settings import load_settings
from vision.cameras.dshow_devices import VideoDevice

BOARD = [f"usb#vid_0bdc&pid_8088&mi_00#7&{n}&0&0000#global" for n in ("aaa", "bbb", "ccc")]
WEBCAM = "usb#vid_0c45&pid_6a09&mi_00#7&ddd&0&0000#global"


def _service(tmp_path, devices: list[int]) -> vs.VisionService:
    cams = [{"id": f"cam{i + 1}", "name": f"Camera {i + 1}", "source": {"type": "opencv", "device": d}}
            for i, d in enumerate(devices)]
    settings = load_settings(extra={"mode": "live", "data_dir": str(tmp_path), "vision": {"cameras": cams}})
    svc = vs.VisionService.__new__(vs.VisionService)
    svc.settings, svc.cfg, svc.simulator = settings, settings.vision, False
    return svc


def _list(*paths: str) -> list[VideoDevice]:
    return [VideoDevice(i, "Integrated Webcam" if p == WEBCAM else "USB Camera", p) for i, p in enumerate(paths)]


def test_laptop_webcam_is_skipped(tmp_path, monkeypatch) -> None:
    # The laptop's webcam is number 0: the default numbers 0, 1, 2 would take it.
    monkeypatch.setattr(vs, "list_video_devices", lambda: _list(WEBCAM, *BOARD))
    svc = _service(tmp_path, [0, 1, 2])
    svc._pin_devices()
    paths = [c.source.device_path for c in svc.cfg.cameras]
    assert WEBCAM not in paths
    assert sorted(paths) == sorted(BOARD)
    assert [c.source.device for c in svc.cfg.cameras] == [3, 1, 2]


def test_pinned_camera_survives_renumbering(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(vs, "list_video_devices", lambda: _list(*BOARD, WEBCAM))
    svc = _service(tmp_path, [0, 1, 2])
    svc._pin_devices()
    pinned = {c.id: c.source.device_path for c in svc.cfg.cameras}
    # A camera dropped off USB and came back: Windows numbers them differently now.
    monkeypatch.setattr(vs, "list_video_devices", lambda: _list(BOARD[2], BOARD[0], WEBCAM, BOARD[1]))
    saved = yaml.safe_load((tmp_path / "runtime.yaml").read_text(encoding="utf-8"))["vision"]["cameras"]
    assert {c["id"]: c["source"]["device_path"] for c in saved} == pinned
    svc._pin_devices()  # nothing to do: all pinned
    assert {c.id: c.source.device_path for c in svc.cfg.cameras} == pinned
    # Opening follows the path to today's number.
    import vision.cameras.dshow_devices as dd
    monkeypatch.setattr(dd, "list_video_devices", lambda: _list(BOARD[2], BOARD[0], WEBCAM, BOARD[1]))
    assert dd.index_for_path(pinned["cam1"]) == 1 and dd.index_for_path(pinned["cam3"]) == 0
