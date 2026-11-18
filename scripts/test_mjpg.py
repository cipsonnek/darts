"""Can a camera be switched to compressed MJPG? (stop DartSense first, it holds the cameras)

    .venv\\Scripts\\python.exe scripts\\test_mjpg.py

Cheap cameras often start in uncompressed YUY2: three of those at 1280x720 do not fit on one
USB adapter and give only a few frames per second. Some switch to MJPG only when the settings
come in a certain order. For every camera this tries three ways and prints the format and the
frames per second each one gives.
"""

from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2  # noqa: E402

API = cv2.CAP_DSHOW
MJPG = cv2.VideoWriter_fourcc(*"MJPG")
W, H, FPS = 1280, 720, 30


def fourcc(cap: cv2.VideoCapture) -> str:
    v = int(cap.get(cv2.CAP_PROP_FOURCC))
    return "".join(chr((v >> 8 * i) & 0xFF) for i in range(4)).strip("\x00 ") or "?"


def fps_of(cap: cv2.VideoCapture, seconds: float = 2.0) -> float:
    for _ in range(3):
        cap.read()
    n, end = 0, time.monotonic() + seconds
    while time.monotonic() < end:
        if cap.read()[0]:
            n += 1
    return n / seconds


def way_format_first(i: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(i, API)
    cap.set(cv2.CAP_PROP_FOURCC, MJPG)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    return cap


def way_size_first(i: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(i, API)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    cap.set(cv2.CAP_PROP_FOURCC, MJPG)
    return cap


def way_at_open(i: int) -> cv2.VideoCapture:
    return cv2.VideoCapture(i, API, [cv2.CAP_PROP_FOURCC, MJPG, cv2.CAP_PROP_FRAME_WIDTH, W,
                                     cv2.CAP_PROP_FRAME_HEIGHT, H, cv2.CAP_PROP_FPS, FPS])


WAYS = [("format, potem rozmiar", way_format_first), ("rozmiar, potem format", way_size_first),
        ("wszystko przy otwarciu", way_at_open)]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(f"OpenCV {cv2.__version__}, DirectShow, cel: MJPG {W}x{H} {FPS} FPS\n")
    for i in range(8):
        probe = cv2.VideoCapture(i, API)
        if not probe.isOpened():
            probe.release()
            continue
        probe.release()
        print(f"numer {i}:")
        for name, way in WAYS:
            try:
                cap = way(i)
                if not cap.isOpened():
                    print(f"   {name:24s} nie otwarta")
                    continue
                fps = fps_of(cap)
                print(f"   {name:24s} format {fourcc(cap):4s} {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
                      f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}  {fps:4.1f} klatek/s")
                cap.release()
            except cv2.error as exc:
                print(f"   {name:24s} błąd: {str(exc).splitlines()[0][:60]}")
            time.sleep(0.5)
        print()


if __name__ == "__main__":
    main()
