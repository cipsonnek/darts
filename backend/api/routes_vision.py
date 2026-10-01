"""Cameras, live streams, calibration, board and detection."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse

from backend.api import deps
from backend.api.schemas import BoardCalibrationIn, CameraPatch, ControlsIn, ResolveIn
from vision.diagnostics.overlays import LAYERS

router = APIRouter(prefix="/api", tags=["vision"])

_VIEWS = "^(raw|undistorted|topdown)$"


def _layers(overlay: str | None) -> set[str]:
    if not overlay:
        return set()
    out = {x.strip() for x in overlay.split(",") if x.strip()}
    bad = out - set(LAYERS) - {"all"}
    if bad:
        raise HTTPException(422, f"unknown overlay layers {sorted(bad)}; valid: {list(LAYERS)}")
    return set(LAYERS) if "all" in out else out


def _cam(vision, camera_id: str):
    try:
        return vision.camera(camera_id)
    except KeyError as exc:
        raise HTTPException(404, f"unknown camera {camera_id}") from exc


# ---------------------------------------------------------------------------- cameras
@router.get("/cameras")
def cameras(vision=Depends(deps.vision)) -> list[dict]:
    return vision.camera_list()


@router.get("/cameras/probe", dependencies=[Depends(deps.require_admin)])
def probe(vision=Depends(deps.vision)) -> list[dict]:
    return vision.probe()


@router.get("/cameras/{camera_id}")
def camera(camera_id: str, vision=Depends(deps.vision)) -> dict:
    _cam(vision, camera_id)
    return next(c for c in vision.camera_list() if c["id"] == camera_id)


@router.patch("/cameras/{camera_id}", dependencies=[Depends(deps.require_admin)])
def patch_camera(camera_id: str, body: CameraPatch, vision=Depends(deps.vision)) -> dict:
    _cam(vision, camera_id)
    try:
        return vision.update_camera(camera_id, body.model_dump(exclude_none=True))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, str(exc)) from exc


@router.post("/cameras/{camera_id}/controls", dependencies=[Depends(deps.require_admin)])
def controls(camera_id: str, body: ControlsIn, vision=Depends(deps.vision)) -> dict:
    _cam(vision, camera_id)
    return vision.apply_controls(camera_id, body.model_dump(exclude_none=True))


@router.get("/cameras/{camera_id}/snapshot.jpg")
def snapshot(camera_id: str, overlay: str | None = None, width: int | None = Query(None, ge=64, le=4096),
             view: str = Query("raw", pattern=_VIEWS), quality: int = Query(85, ge=10, le=100),
             vision=Depends(deps.vision)) -> Response:
    _cam(vision, camera_id)
    data = vision.render_view(camera_id, width, _layers(overlay), view, quality)
    if data is None:
        raise HTTPException(503, "no frame available (camera disconnected?)")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/cameras/{camera_id}/stream.mjpg")
async def stream(camera_id: str, overlay: str | None = None, width: int | None = Query(None, ge=64, le=4096),
                 fps: float | None = Query(None, ge=0.5, le=30), view: str = Query("raw", pattern=_VIEWS),
                 quality: int | None = Query(None, ge=10, le=100), vision=Depends(deps.vision)):
    _cam(vision, camera_id)
    return StreamingResponse(vision.mjpeg(camera_id, width, fps, _layers(overlay), view, quality),
                             media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------- calibration
@router.get("/calibration")
def calibration(vision=Depends(deps.vision)) -> dict:
    return {"cameras": vision.calibration_status(), "overall": vision.calibration_overall()}


@router.get("/calibration/landmarks")
def landmarks(vision=Depends(deps.vision)) -> dict:
    return vision.landmarks()


@router.get("/calibration/charuco.png")
def charuco(vision=Depends(deps.vision)) -> Response:
    cfg = vision.cfg.calibration
    return Response(vision.charuco_png(), media_type="image/png",
                    headers={"Content-Disposition": "inline; filename=charuco_target.png",
                             "X-Target": f"{cfg.charuco_squares_x}x{cfg.charuco_squares_y} squares, "
                                         f"{cfg.charuco_square_mm} mm, print at 300 dpi"})


@router.post("/calibration/validate")
def validate(vision=Depends(deps.vision)) -> dict:
    return vision.validate_now()


@router.post("/calibration/{camera_id}/board", dependencies=[Depends(deps.require_admin)])
def detect_board(camera_id: str, body: BoardCalibrationIn, vision=Depends(deps.vision)) -> dict:
    _cam(vision, camera_id)
    try:
        return vision.detect_board(camera_id, body.method, body.points, body.hint, body.azimuth_deg)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/calibration/{camera_id}/preview.jpg")
def preview(camera_id: str, width: int | None = Query(None, ge=64, le=4096), vision=Depends(deps.vision)) -> Response:
    _cam(vision, camera_id)
    data = vision.preview_pose(camera_id, width)
    if data is None:
        raise HTTPException(503, "no frame available")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/calibration/{camera_id}/board/accept", dependencies=[Depends(deps.require_admin)])
def accept_board(camera_id: str, vision=Depends(deps.vision), games=Depends(deps.games)) -> dict:
    _cam(vision, camera_id)
    try:
        return vision.accept_pose(camera_id)
    except KeyError as exc:
        raise HTTPException(409, "no pending calibration — run detection first") from exc


@router.post("/calibration/{camera_id}/board/discard", dependencies=[Depends(deps.require_admin)])
def discard_board(camera_id: str, vision=Depends(deps.vision)) -> dict:
    vision.discard_pose(camera_id)
    return {"discarded": True}


@router.delete("/calibration/{camera_id}/board", dependencies=[Depends(deps.require_admin)])
def clear_board(camera_id: str, vision=Depends(deps.vision)) -> dict:
    _cam(vision, camera_id)
    vision.clear_pose(camera_id)
    return {"cleared": True}


@router.post("/calibration/{camera_id}/intrinsics/start", dependencies=[Depends(deps.require_admin)])
def intrinsics_start(camera_id: str, vision=Depends(deps.vision)) -> dict:
    _cam(vision, camera_id)
    try:
        return vision.intrinsics_start(camera_id)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/calibration/{camera_id}/intrinsics/capture", dependencies=[Depends(deps.require_admin)])
def intrinsics_capture(camera_id: str, vision=Depends(deps.vision)) -> dict:
    try:
        return vision.intrinsics_capture(camera_id)
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/calibration/{camera_id}/intrinsics/solve", dependencies=[Depends(deps.require_admin)])
def intrinsics_solve(camera_id: str, vision=Depends(deps.vision)) -> dict:
    try:
        return vision.intrinsics_solve(camera_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/calibration/{camera_id}/intrinsics/accept", dependencies=[Depends(deps.require_admin)])
def intrinsics_accept(camera_id: str, vision=Depends(deps.vision), games=Depends(deps.games)) -> dict:
    try:
        return vision.intrinsics_accept(camera_id)
    except KeyError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/calibration/{camera_id}/intrinsics/session", dependencies=[Depends(deps.require_admin)])
def intrinsics_cancel(camera_id: str, vision=Depends(deps.vision)) -> dict:
    vision.intrinsics_cancel(camera_id)
    return {"cancelled": True}


@router.get("/calibration/{camera_id}/history")
def calibration_history(camera_id: str, games=Depends(deps.games)) -> list[dict]:
    from sqlalchemy import select

    from backend.database.models import CalibrationProfile

    with games.db.session() as s:
        rows = s.scalars(select(CalibrationProfile).where(CalibrationProfile.camera_id == camera_id)
                         .order_by(CalibrationProfile.created_at.desc()).limit(50))
        return [{"id": r.id, "kind": r.kind, "created_at": r.created_at.isoformat(), "grade": r.grade,
                 "method": r.method, "metrics": r.metrics} for r in rows]


# ---------------------------------------------------------------------------- board & detection
@router.get("/board")
def board(vision=Depends(deps.vision)) -> dict:
    return vision.board.describe()


@router.get("/board/state")
def board_state(vision=Depends(deps.vision)) -> dict:
    eng = vision.engine
    return {"darts": [d.to_dict() for d in eng.board_state.darts] if eng else [], "state": eng.state.value if eng else None}


@router.post("/board/reset")
def board_reset(mark_empty: bool = True, vision=Depends(deps.vision)) -> dict:
    removed = vision.engine.reset_board(mark_empty) if vision.engine else []
    return {"removed": [d.dart_id for d in removed], "marked_empty": mark_empty}


@router.get("/detection/status")
def detection_status(vision=Depends(deps.vision)) -> dict:
    return vision.engine.status() if vision.engine else {}


@router.get("/detection/latest")
def detection_latest(vision=Depends(deps.vision)) -> dict | None:
    return vision.engine.last_detection if vision.engine else None


@router.get("/detection/debug")
def detection_debug(vision=Depends(deps.vision)) -> dict:
    return vision.debug_snapshot()


@router.post("/detection/pause")
def detection_pause(paused: bool = True, vision=Depends(deps.vision)) -> dict:
    if vision.engine:
        vision.engine.pause(paused)
    return {"paused": paused}


@router.get("/detections")
def detections(limit: int = Query(50, ge=1, le=1000), game_id: str | None = None, games=Depends(deps.games)) -> list[dict]:
    return games.recent_detections(limit, game_id)


@router.get("/detections/pending")
def pending(game_id: str | None = None, games=Depends(deps.games)) -> list[dict]:
    return games.pending(game_id)


@router.get("/detections/{detection_id}")
def detection(detection_id: str, games=Depends(deps.games)) -> dict:
    try:
        return games.detection(detection_id)
    except KeyError as exc:
        raise HTTPException(404, "unknown detection") from exc


@router.post("/detections/{detection_id}/resolve")
def resolve(detection_id: str, body: ResolveIn, games=Depends(deps.games)) -> dict[str, Any]:
    from backend.game_engine import GameError

    try:
        return games.resolve(detection_id, body.choice, body.label, body.x_mm, body.y_mm)
    except KeyError as exc:
        raise HTTPException(404, "unknown detection") from exc
    except GameError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/corrections")
def corrections(limit: int = Query(100, ge=1, le=1000), games=Depends(deps.games)) -> list[dict]:
    return games.corrections(limit)
