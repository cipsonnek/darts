"""End-to-end API tests: the real application in simulator mode (three synthetic cameras,
real engine, real database), driven through REST and WebSocket."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.settings import load_settings

pytestmark = pytest.mark.slow


def _settings(tmp_path, **server):
    cams = [{"id": f"cam{i}", "name": f"Sim {i}", "source": {"type": "synthetic"}, "width": 960, "height": 540,
             "fps": 12, "mount": {"azimuth_deg": az}} for i, az in ((1, 0), (2, 120), (3, 240))]
    return load_settings(extra={
        "mode": "simulator",
        "data_dir": str(tmp_path / "data"),
        "database": {"url": f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}"},
        "logging": {"directory": str(tmp_path / "logs"), "json": False},
        "server": {"serve_frontend": False, **server},
        "vision": {"cameras": cams, "calibration_dir": str(tmp_path / "calib"),
                   "recording": {"directory": str(tmp_path / "rec")}, "validation": {"enabled": False},
                   "simulator": {"seed": 3}},
    })


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("app")
    app = create_app(_settings(tmp))
    with TestClient(app) as c:
        # wait for frames from all cameras
        for _ in range(100):
            cams = c.get("/api/cameras").json()
            if all(cm["health"] and cm["health"]["frames_total"] > 3 for cm in cams):
                break
            time.sleep(0.1)
        yield c


def _wait_for(ws, type_: str, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = json.loads(ws.receive_text())
        if msg.get("type") == type_:
            return msg
    raise AssertionError(f"no {type_} within {timeout}s")


def test_health_and_cameras(client) -> None:
    h = client.get("/api/health").json()
    assert h["mode"] == "simulator" and h["cameras_total"] == 3
    cams = client.get("/api/cameras").json()
    assert {c["id"] for c in cams} == {"cam1", "cam2", "cam3"}
    assert all(c["synthetic"] for c in cams)
    r = client.get("/api/cameras/cam1/snapshot.jpg?width=320&overlay=info")
    assert r.status_code == 200 and r.content[:2] == b"\xff\xd8"
    assert client.get("/api/cameras/nope/snapshot.jpg").status_code == 404
    assert client.get("/api/cameras/cam1/snapshot.jpg?overlay=bogus").status_code == 422


def test_board_geometry_endpoint(client) -> None:
    b = client.get("/api/board").json()
    assert b["radii_mm"]["double_outer"] == 170.0
    assert b["sector_order"][0] == 20


def test_calibration_flow(client) -> None:
    res = client.post("/api/simulator/auto-calibrate").json()
    assert all(v["ok"] for v in res.values()), res
    cal = client.get("/api/calibration").json()
    for cid, c in cal["cameras"].items():
        assert c["pose"] is not None and c["pose"]["grade"] in ("good", "fair")
    assert client.get("/api/calibration/landmarks").json()["standard"]
    png = client.get("/api/calibration/charuco.png")
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    hist = client.get("/api/calibration/cam1/history").json()
    assert hist and hist[0]["kind"] == "pose"


def test_players_and_validation(client) -> None:
    r = client.post("/api/players", json={"name": "Alice", "color": "#22cc88"})
    assert r.status_code == 201
    assert client.post("/api/players", json={"name": "alice"}).status_code == 409  # duplicate
    assert client.post("/api/players", json={"name": "Bob", "color": "red"}).status_code == 422
    assert client.post("/api/players", json={"name": ""}).status_code == 422
    client.post("/api/players", json={"name": "Bob"})
    names = [p["name"] for p in client.get("/api/players").json()]
    assert names == ["Alice", "Bob"]


def test_game_with_detected_darts(client) -> None:
    players = {p["name"]: p["id"] for p in client.get("/api/players").json()}
    g = client.post("/api/games", json={"mode": "x01", "settings": {"start_score": 301},
                                        "player_ids": [players["Alice"], players["Bob"]]}).json()
    gid = g["id"]
    assert g["status"] == "running" and g["player_summaries"][0]["remaining"] == 301
    # let the engine settle a baseline after calibration
    for _ in range(80):
        if client.get("/api/detection/status").json()["state"] == "idle":
            break
        time.sleep(0.1)
    with client.websocket_connect("/ws/events") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["type"] == "hello"
        client.post("/api/simulator/throw", json={"label": "T20"})
        dart = _wait_for(ws, "dart_detected")
        assert dart["data"]["score"]["label"] in ("T20", "S20", "T1", "T5")
        state = _wait_for(ws, "game_state")
    game = client.get(f"/api/games/{gid}").json()
    if game["pending"]:
        d = game["pending"][0]
        game = client.post(f"/api/detections/{d['id']}/resolve", json={"choice": "label", "label": "T20"}).json()
    assert game["player_summaries"][0]["remaining"] == 241
    # manual dart, undo, correction
    game = client.post(f"/api/games/{gid}/darts", json={"label": "S5"}).json()
    assert game["player_summaries"][0]["remaining"] == 236
    game = client.post(f"/api/games/{gid}/undo").json()
    assert game["player_summaries"][0]["remaining"] == 241
    first = game["state"]["turns"][0]["darts"][0]["dart_id"]
    game = client.post(f"/api/games/{gid}/corrections", json={"dart_id": first, "label": "T19"}).json()
    assert game["player_summaries"][0]["remaining"] == 301 - 57
    assert client.post(f"/api/games/{gid}/darts", json={"label": "T25"}).status_code == 422
    corr = client.get("/api/corrections").json()
    assert corr[0]["corrected"] == "T19"
    # takeout advances the turn automatically after three darts
    for lbl in ("S1", "S1"):
        client.post(f"/api/games/{gid}/darts", json={"label": lbl})
    assert client.get(f"/api/games/{gid}").json()["state"]["awaiting_takeout"]
    client.post("/api/simulator/takeout")
    for _ in range(100):
        game = client.get(f"/api/games/{gid}").json()
        if not game["state"]["awaiting_takeout"]:
            break
        time.sleep(0.1)
    assert game["state"]["current_player"] == 1


def test_stats_and_lists(client) -> None:
    players = {p["name"]: p["id"] for p in client.get("/api/players").json()}
    st = client.get(f"/api/stats/players/{players['Alice']}").json()
    assert st["darts_thrown"] >= 3 and st["x01"]["average_3_dart"] is not None
    assert client.get("/api/stats/overview").json()["games"] >= 1
    assert isinstance(client.get("/api/stats/heatmap").json(), list)
    assert client.get("/api/games").json()
    assert client.get("/api/detections?limit=5").status_code == 200
    assert client.get("/api/game-modes").json()


def test_diagnostics_logs_settings(client) -> None:
    d = client.get("/api/diagnostics").json()
    assert d["engine"]["state"] in ("idle", "motion", "processing", "starting", "obstructed")
    assert "detection_debug" in d
    assert isinstance(client.get("/api/logs?limit=10").json(), list)
    assert client.get("/api/logs?level=NOPE").status_code == 422
    s = client.get("/api/settings").json()
    assert s["mode"] == "simulator"
    r = client.put("/api/settings/vision", json={"scoring": {"confidence_threshold": 0.85}})
    assert r.status_code == 200
    assert client.get("/api/settings").json()["vision"]["scoring"]["confidence_threshold"] == 0.85
    bad = client.put("/api/settings/vision", json={"scoring": {"confidence_threshold": 3}})
    assert bad.status_code == 422
    assert client.put("/api/settings/ui/theme", json={"value": {"name": "neon"}}).status_code == 200


def test_recording_cycle(client) -> None:
    r = client.post("/api/recordings/start", json={"name": "t1"})
    assert r.status_code == 200
    time.sleep(1.0)
    assert client.post("/api/recordings/start", json={"name": "t2"}).status_code == 409
    s = client.post("/api/recordings/stop").json()
    assert all(v > 0 for v in s["frame_counts"].values())
    detail = client.get("/api/recordings/t1").json()
    assert detail["metadata"]["synthetic"] is True
    idx = detail["frames"]["cam1"][0]["index"]
    img = client.get(f"/api/recordings/t1/frames/cam1/{idx}.jpg")
    assert img.status_code == 200
    assert client.get("/api/recordings/..%2F..%2Fetc").status_code == 404


def test_admin_token_mode(tmp_path) -> None:
    app = create_app(_settings(tmp_path, admin_auth="token", admin_token="s3cret"), start_vision=False)
    with TestClient(app) as c:
        assert c.get("/api/admin/check").status_code == 401
        assert c.get("/api/admin/check", headers={"X-Admin-Token": "wrong"}).status_code == 401
        assert c.get("/api/admin/check", headers={"X-Admin-Token": "s3cret"}).status_code == 200
