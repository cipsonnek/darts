"""Assigning USB devices to camera slots from the UI."""

from __future__ import annotations

import numpy as np

from backend.services.vision_service import VisionService
from backend.settings import load_settings
from backend.ws.hub import EventHub
from vision.geometry.camera_model import CameraModel, default_intrinsics


class _Manager:
    def __init__(self) -> None:
        self.restarted: list[list[str]] = []

    def reconfigure_many(self, configs) -> None:
        self.restarted.append([c.id for c in configs])

    def health(self) -> list[dict]:
        return []


def _service(tmp_path) -> VisionService:
    cams = [{"id": f"cam{i}", "name": f"Camera {i} (by the {n})", "source": {"type": "opencv", "device": d},
             "mount": {"azimuth_deg": az, "description": f"by the {n}"}}
            for i, d, n, az in ((1, 0, 10, 108), (2, 2, 20, 350), (3, 3, 16, 225))]
    settings = load_settings(extra={"mode": "live", "data_dir": str(tmp_path / "data"),
                                    "vision": {"cameras": cams, "calibration_dir": str(tmp_path / "calib")}})
    vs = VisionService(settings, EventHub())
    vs.manager = _Manager()
    return vs


def _pose(vs: VisionService, cid: str, fx: float) -> None:
    K = default_intrinsics(1280, 720)
    K[0, 0] = K[1, 1] = fx
    cam = CameraModel(K=K, dist=np.zeros(5), R=np.eye(3), t=np.array([0, 0, 500.0]),
                      image_size=(1280, 720), camera_id=cid)
    vs.store.save_pose(cid, cam, "auto", {}, "fair", "estimated")


def test_assign_used_device_swaps_devices_and_calibrations(tmp_path) -> None:
    vs = _service(tmp_path)
    _pose(vs, "cam1", 700.0)
    _pose(vs, "cam3", 900.0)
    res = vs.assign_device("cam1", 3)
    assert res["swapped_with"] == "cam3" and res["recalibrate"] == []
    assert vs.camera("cam1").source.device == 3 and vs.camera("cam3").source.device == 0
    # Calibrations follow the physical cameras.
    assert vs.store.camera_model("cam1").K[0, 0] == 900.0
    assert vs.store.camera_model("cam3").K[0, 0] == 700.0
    assert vs.store.camera_model("cam1").camera_id == "cam1"
    assert vs.manager.restarted == [["cam1", "cam3"]]
    # So does the mount position (and the note in the name).
    assert vs.camera("cam1").mount.azimuth_deg == 225 and vs.camera("cam1").name == "Camera 1 (by the 16)"
    assert vs.camera("cam3").mount.azimuth_deg == 108 and vs.camera("cam3").name == "Camera 3 (by the 10)"
    # Persisted for the next start.
    again = load_settings(extra={"mode": "live", "data_dir": str(tmp_path / "data")})
    assert {c.id: c.source.device for c in again.vision.cameras} == {"cam1": 3, "cam2": 2, "cam3": 0}


def test_assign_free_device_marks_calibration_stale(tmp_path) -> None:
    vs = _service(tmp_path)
    _pose(vs, "cam2", 700.0)
    res = vs.assign_device("cam2", 5)
    assert res["swapped_with"] is None and res["recalibrate"] == ["cam2"]
    assert vs.camera("cam2").source.device == 5
    assert vs.store.camera_model("cam2") is None


def test_assign_same_device_is_a_no_op(tmp_path) -> None:
    vs = _service(tmp_path)
    assert vs.assign_device("cam1", 0)["recalibrate"] == []
    assert vs.manager.restarted == []
