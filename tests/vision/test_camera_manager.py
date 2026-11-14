"""Changing where a camera stands must not restart it (a USB restart can drop cameras)."""

from __future__ import annotations

from vision.cameras.manager import CameraManager
from vision.config import CameraConfig
from vision.simulation.world import SimulatedWorld


def _manager(sim_rig) -> tuple[CameraManager, CameraConfig]:
    cfg = CameraConfig.model_validate({"id": "cam1", "name": "Camera 1", "source": {"type": "synthetic"},
                                       "width": 960, "height": 540})
    return CameraManager([cfg], world=SimulatedWorld(sim_rig, seed=1)), cfg


def test_mount_change_keeps_the_camera_running(sim_rig) -> None:
    mgr, cfg = _manager(sim_rig)
    before = mgr.worker(cfg.id)
    moved = CameraConfig.model_validate({**cfg.model_dump(), "mount": {"azimuth_deg": 126.0, "description": "przy 15"},
                                         "name": "Kamera przy 15"})
    mgr.reconfigure(moved)
    assert mgr.worker(cfg.id) is before
    assert before.camera.config.mount.azimuth_deg == 126.0
    assert mgr.configs[cfg.id].name == "Kamera przy 15"


def test_new_device_restarts_the_camera(sim_rig) -> None:
    mgr, cfg = _manager(sim_rig)
    before = mgr.worker(cfg.id)
    mgr.reconfigure(CameraConfig.model_validate({**cfg.model_dump(), "width": 640, "height": 360}))
    assert mgr.worker(cfg.id) is not before
    mgr.stop()
