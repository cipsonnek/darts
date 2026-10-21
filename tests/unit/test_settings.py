"""Settings layering: UI overrides are stored per mode."""

from __future__ import annotations

from backend.settings import load_settings, save_runtime_overrides


def test_live_overrides_do_not_leak_into_simulator(tmp_path) -> None:
    data = str(tmp_path / "data")
    live = load_settings(extra={"mode": "live", "data_dir": data})
    save_runtime_overrides(live, {"vision": {"scoring": {"confidence_threshold": 0.42}}})
    assert live.runtime_file.name == "runtime.yaml"
    assert load_settings(extra={"mode": "live", "data_dir": data}).vision.scoring.confidence_threshold == 0.42

    sim = load_settings(extra={"mode": "simulator", "data_dir": data})
    assert sim.runtime_file.name == "runtime-simulator.yaml"
    assert sim.vision.scoring.confidence_threshold != 0.42
    save_runtime_overrides(sim, {"vision": {"scoring": {"confidence_threshold": 0.5}}})
    assert load_settings(extra={"mode": "simulator", "data_dir": data}).vision.scoring.confidence_threshold == 0.5
    assert load_settings(extra={"mode": "live", "data_dir": data}).vision.scoring.confidence_threshold == 0.42
