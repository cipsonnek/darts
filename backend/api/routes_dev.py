"""Developer tools: recordings, replay evaluation, ground-truth annotation, simulator."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend.api import deps
from backend.api.schemas import AnnotationIn, RecordingIn, SimLightingIn, SimThrowIn

router = APIRouter(prefix="/api", tags=["developer"])


def _rec(vision, name: str):
    try:
        return vision.recording_path(name)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, "unknown recording") from exc


@router.get("/recordings")
def recordings(vision=Depends(deps.vision)) -> dict:
    return {"recordings": vision.recordings(), "active": vision.recording_status()}


@router.post("/recordings/start")
def start_recording(body: RecordingIn, vision=Depends(deps.vision)) -> dict:
    try:
        return vision.start_recording(body.name, body.notes)
    except (RuntimeError, FileExistsError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/recordings/stop")
def stop_recording(vision=Depends(deps.vision)) -> dict:
    res = vision.stop_recording()
    if res is None:
        raise HTTPException(409, "not recording")
    return res


@router.get("/recordings/{name}")
def recording(name: str, vision=Depends(deps.vision)) -> dict:
    _rec(vision, name)
    return vision.recording_detail(name)


@router.delete("/recordings/{name}", dependencies=[Depends(deps.require_admin)], status_code=204)
def delete_recording(name: str, vision=Depends(deps.vision)) -> None:
    import shutil

    shutil.rmtree(_rec(vision, name))


@router.get("/recordings/{name}/frames/{camera_id}/{index}.jpg")
def recording_frame(name: str, camera_id: str, index: int, overlay: str | None = None,
                    width: int | None = Query(None, ge=64, le=4096), vision=Depends(deps.vision)) -> Response:
    _rec(vision, name)
    if not camera_id.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(422, "invalid camera id")
    layers = {x for x in (overlay or "").split(",") if x}
    data = vision.recording_frame(name, camera_id, index, layers, width)
    if data is None:
        raise HTTPException(404, "frame not found")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@router.get("/recordings/{name}/pixel-to-board")
def pixel_to_board(name: str, camera_id: str, x: float, y: float, vision=Depends(deps.vision)) -> dict:
    _rec(vision, name)
    p = vision.recording_pixel_to_board(name, camera_id, x, y)
    if p is None:
        raise HTTPException(409, "camera not calibrated in this recording or point not on the board plane")
    return {"x_mm": p[0], "y_mm": p[1], "score": vision.board.score(*p).to_dict()}


@router.post("/recordings/{name}/ground-truth")
def annotate(name: str, body: AnnotationIn, vision=Depends(deps.vision)) -> list[dict]:
    _rec(vision, name)
    for e in body.entries:
        if not isinstance(e.get("x_mm"), (int, float)) or not isinstance(e.get("y_mm"), (int, float)):
            raise HTTPException(422, "each entry needs numeric x_mm and y_mm")
    return vision.annotate(name, body.entries)


@router.post("/recordings/{name}/evaluate")
def evaluate(name: str, vision=Depends(deps.vision)) -> dict:
    _rec(vision, name)
    return vision.evaluate_recording(name)


# ---------------------------------------------------------------------------- simulator
def _sim(fn, *a):
    try:
        return fn(*a)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/simulator/throw")
def sim_throw(body: SimThrowIn, vision=Depends(deps.vision)) -> dict:
    return _sim(vision.sim_throw, body.target, body.scatter_mm, body.label)


@router.post("/simulator/takeout")
def sim_takeout(vision=Depends(deps.vision)) -> dict:
    return _sim(vision.sim_takeout)


@router.post("/simulator/lighting")
def sim_lighting(body: SimLightingIn, vision=Depends(deps.vision)) -> dict:
    return _sim(vision.sim_lighting, body.preset)


@router.post("/simulator/hand")
def sim_hand(vision=Depends(deps.vision)) -> dict:
    return _sim(vision.sim_hand)


@router.get("/simulator/ground-truth")
def sim_gt(vision=Depends(deps.vision)) -> list[dict]:
    return _sim(vision.sim_ground_truth)


@router.post("/simulator/auto-calibrate")
def sim_autocal(vision=Depends(deps.vision)) -> dict:
    _sim(vision.require_simulator)
    return vision.sim_auto_calibrate()


# ---------------------------------------------------------------------------- benchmarks
@router.get("/benchmarks/latest")
def latest_benchmark() -> dict:
    """The most recent synthetic benchmark report (scripts/benchmark.py)."""
    import json

    from backend.settings import ROOT

    p = ROOT / "docs" / "benchmarks" / "latest.json"
    if not p.exists():
        raise HTTPException(404, "no benchmark has been run yet (python scripts/benchmark.py)")
    return json.loads(p.read_text(encoding="utf-8"))
