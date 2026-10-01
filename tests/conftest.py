from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def sim_rig():
    """A jittered 3-camera rig at 960x540 (faster than 1280x720, same geometry)."""
    from vision.simulation.rig import default_rig

    return default_rig(960, 540, jitter_seed=3)


@pytest.fixture(scope="session")
def board():
    from vision.geometry.board import BoardGeometry

    return BoardGeometry()
