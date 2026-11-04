"""Camera check without the server (stop DartSense first, it would hold the cameras).

    .venv\\Scripts\\python.exe scripts\\test_cameras.py

Part 1 opens every device number on its own: shows how many devices exist and which numbers
they have. Part 2 opens the working ones at the same time, as the board does. A camera that
works alone but not together with the others points to USB bandwidth or power.
"""

from __future__ import annotations

import os
import platform
import sys
import time

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")  # no warning for every free device number

import cv2  # noqa: E402

API = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
MAX_INDEX = 8
MODES = [(1280, 720, 30), (1280, 720, 15), (640, 480, 30)]


def fourcc_name(cap: cv2.VideoCapture) -> str:
    v = int(cap.get(cv2.CAP_PROP_FOURCC))
    return "".join(chr((v >> 8 * i) & 0xFF) for i in range(4)).strip("\x00 ") or "?"


def configure(cap: cv2.VideoCapture, width: int, height: int, fps: int) -> None:
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)


def alone() -> list[int]:
    print("1) Kazde urzadzenie osobno")
    found = []
    for i in range(MAX_INDEX):
        cap = cv2.VideoCapture(i, API)
        if not cap.isOpened():
            cap.release()
            continue
        configure(cap, 1280, 720, 30)
        good = sum(1 for _ in range(10) if cap.read()[0])
        ok, img = cap.read()
        blank = ok and img is not None and float(img.std()) < 3.0
        print(f"   numer {i}: klatki {good}/10, {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
              f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}, format {fourcc_name(cap)}"
              f"{'  (pusty obraz - moze kamera wirtualna)' if blank else ''}")
        cap.release()
        if good:
            found.append(i)
    if not found:
        print("   Nie znaleziono zadnej dzialajacej kamery.")
    return found


def together(devices: list[int], width: int, height: int, fps: int) -> None:
    print(f"\n2) Wszystkie razem: {width}x{height}, {fps} FPS")
    caps = {}
    for i in devices:
        cap = cv2.VideoCapture(i, API)
        if cap.isOpened():
            configure(cap, width, height, fps)
        caps[i] = cap
    counts = dict.fromkeys(devices, 0)
    end = time.monotonic() + 4
    while time.monotonic() < end:
        for i, cap in caps.items():
            if cap.isOpened() and cap.read()[0]:
                counts[i] += 1
    for i, cap in caps.items():
        print(f"   numer {i}: {'otwarta' if cap.isOpened() else 'NIE OTWARTA'}, klatek w 4 s: {counts[i]}, "
              f"format {fourcc_name(cap) if cap.isOpened() else '-'}")
        cap.release()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(f"OpenCV {cv2.__version__}\n")
    found = alone()
    print(f"\nDzialajace numery: {found}")
    if len(found) > 1:
        for mode in MODES:
            together(found, *mode)


if __name__ == "__main__":
    main()
