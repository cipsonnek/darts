"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import __version__
from backend.api import routes_dev, routes_fleet, routes_games, routes_system, routes_vision
from backend.database import Database
from backend.logging_setup import configure_logging
from backend.services.fleet_client import FleetReporter
from backend.services.fleet_service import FleetService
from backend.services.game_service import GameService
from backend.services.stats_service import StatsService
from backend.services.vision_service import VisionService
from backend.settings import ROOT, AppSettings, ensure_admin_token, load_settings
from backend.ws.hub import EventHub

log = logging.getLogger("backend")


def create_app(settings: AppSettings | None = None, start_vision: bool = True) -> FastAPI:
    settings = settings or load_settings()
    central = settings.mode == "central"
    # The central fleet server has no cameras: the vision engine is never started there.
    start_vision = start_vision and not central

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings.logging.level, settings.path(settings.logging.directory),
                          settings.logging.json_format)
        token = ensure_admin_token(settings)
        log.info("starting DartSense", extra={"version": __version__, "mode": settings.mode,
                                               "admin_auth": settings.server.admin_auth})
        if settings.server.admin_auth != "off":
            log.info("admin token stored in data/admin_token.txt (needed for admin actions from other devices)",
                     extra={"token_prefix": token[:4]})
        db = Database(settings.database.url)
        db.migrate()
        hub = EventHub()
        hub.bind_loop(asyncio.get_running_loop())
        vision = VisionService(settings, hub)
        games = GameService(db, hub)
        games.vision = vision
        vision.profile_sink = lambda cid, kind, data: _store_profile(db, cid, kind, data)
        stats = StatsService(db, games)
        app.state.settings = settings
        app.state.db = db
        app.state.hub = hub
        app.state.vision = vision
        app.state.games = games
        app.state.stats = stats
        app.state.fleet = FleetService(db, settings.fleet)
        reporter = FleetReporter(settings, db, vision)
        app.state.fleet_reporter = reporter

        # Engine events are handed to a single consumer task so that game logic and
        # database writes for vision events are serialised and never block the engine.
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

        def enqueue(ev) -> None:
            def put() -> None:
                if queue.full():
                    log.error("vision event queue full; dropping event", extra={"type": ev.type})
                    return
                queue.put_nowait(ev)
            loop.call_soon_threadsafe(put)

        async def consumer() -> None:
            while True:
                ev = await queue.get()
                try:
                    await asyncio.to_thread(games.on_vision_event, ev)
                except Exception:  # noqa: BLE001
                    log.exception("vision event consumer failed")

        vision.add_event_callback(enqueue)
        consumer_task = asyncio.create_task(consumer(), name="vision-events")
        status_task = asyncio.create_task(_status_broadcaster(app), name="status-broadcast")
        report_task = asyncio.create_task(reporter.run(), name="fleet-report") if not central and reporter.enabled else None
        if start_vision:
            await asyncio.to_thread(vision.start)
        try:
            yield
        finally:
            status_task.cancel()
            consumer_task.cancel()
            if report_task:
                report_task.cancel()
            if start_vision:
                await asyncio.to_thread(vision.stop)
            log.info("DartSense stopped")

    app = FastAPI(title="DartSense", version=__version__, lifespan=lifespan,
                  description="Three-camera automatic dart scoring — REST and WebSocket API")
    app.add_middleware(CORSMiddleware, allow_origins=settings.server.cors_origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["*"])

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # noqa: ANN202
        log.exception("unhandled error", extra={"path": request.url.path})
        return JSONResponse({"detail": "internal error", "error": type(exc).__name__}, status_code=500)

    app.include_router(routes_system.router)
    app.include_router(routes_vision.router)
    app.include_router(routes_games.router)
    app.include_router(routes_dev.router)
    if central:
        app.include_router(routes_fleet.ingest)
        app.include_router(routes_fleet.router)

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket) -> None:
        """Game, detection and system events (low rate)."""
        hub: EventHub = ws.app.state.hub
        vision: VisionService = ws.app.state.vision
        hello = {"version": __version__, "mode": settings.mode,
                 "engine": vision.engine.state.value if vision.engine else None}
        await hub.serve(ws, {"events", "game", "calibration", "system"}, hello)

    @app.websocket("/ws/detection")
    async def ws_detection(ws: WebSocket) -> None:
        """Live diagnostics: engine state, motion levels, camera health (a few Hz)."""
        hub: EventHub = ws.app.state.hub
        await hub.serve(ws, {"detection", "status"}, {"channels": ["detection", "status"]})

    dist = ROOT / "frontend" / "dist"
    if settings.server.serve_frontend and dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):  # noqa: ANN202
            if path == "api" or path.startswith(("api/", "ws/")):
                # An unknown API route is an error, not a page of the UI.
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            target = (dist / path).resolve()
            if path and target.is_file() and dist.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app


def _store_profile(db: Database, camera_id: str, kind: str, data: dict) -> None:
    """Keep a calibration history in the database (the active profile lives in
    data/calibration as JSON so the vision engine can run without the database)."""
    from backend.database.models import CalibrationProfile

    with db.session() as s:
        s.query(CalibrationProfile).filter(CalibrationProfile.camera_id == camera_id,
                                           CalibrationProfile.kind == kind).update({"active": False})
        metrics = data.get("metrics") or {k: data.get(k) for k in ("rms_px", "n_views", "coverage") if k in data}
        s.add(CalibrationProfile(camera_id=camera_id, kind=kind, grade=data.get("grade"), method=data.get("method"),
                                 metrics=metrics, data=data, active=True))


async def _status_broadcaster(app: FastAPI) -> None:
    """Pushes camera health and engine status to /ws/detection a few times per second."""
    while True:
        await asyncio.sleep(0.5)
        try:
            vision: VisionService = app.state.vision
            hub: EventHub = app.state.hub
            if hub.client_count == 0 or vision.engine is None or vision.manager is None:
                continue
            eng = vision.engine
            hub.publish("status", "status", {
                "engine": {"state": eng.state.value, "darts_on_board": len(eng.board_state),
                           "stats": eng.stats.to_dict()},
                "cameras": vision.manager.health(),
                "motion": {cid: round(ctx.last_motion_fraction, 5) for cid, ctx in eng.cameras.items()},
                "sync_spread_ms": round(vision.manager.frameset().sync_spread_ms, 2),
                "recording": vision.recording_status(),
            })
        except Exception:  # noqa: BLE001
            log.exception("status broadcast failed")
