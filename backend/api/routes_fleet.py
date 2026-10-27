"""Fleet management API (central server only).

``/api/fleet/*`` is the operator panel and needs a signed-in operator (``/api/auth/login``).
``/api/fleet/ingest/*`` is called by the boards and authenticates with ``X-Board-Key``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, TypeVar

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.api import deps
from backend.services.fleet_service import FleetError, FleetService, NotFound

T = TypeVar("T")


def fleet(request: Request) -> FleetService:
    return request.app.state.fleet


def _wrap(fn: Callable[..., T], *a: Any) -> T:
    try:
        return fn(*a)
    except NotFound as e:
        raise HTTPException(404, str(e)) from e
    except FleetError as e:
        raise HTTPException(400, str(e)) from e


# ---------------------------------------------------------------------------- schemas
class VenueIn(BaseModel):
    name: str | None = Field(None, max_length=120)
    kind: str | None = None
    address: str | None = Field(None, max_length=200)
    city: str | None = Field(None, max_length=80)
    postal_code: str | None = Field(None, max_length=16)
    lat: float | None = None
    lng: float | None = None
    contact_name: str | None = Field(None, max_length=120)
    phone: str | None = Field(None, max_length=40)
    email: str | None = Field(None, max_length=120)
    opening_hours: str | None = Field(None, max_length=200)
    price_per_game: float | None = None
    venue_share_pct: float | None = None
    notes: str | None = None
    active: bool | None = None


class BoardIn(BaseModel):
    name: str | None = Field(None, max_length=80)
    venue_id: str | None = None
    serial: str | None = Field(None, max_length=64)
    status: str | None = None
    installed_at: datetime | None = None
    notes: str | None = None


class TicketIn(BaseModel):
    title: str | None = Field(None, max_length=200)
    description: str | None = None
    category: str | None = None
    priority: str | None = None
    status: str | None = None
    assignee: str | None = Field(None, max_length=80)
    board_id: str | None = None
    venue_id: str | None = None
    reporter: str | None = Field(None, max_length=80)
    comment: str | None = None
    author: str | None = Field(None, max_length=80)


class CommentIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    author: str = Field("", max_length=80)


class CameraBeat(BaseModel):
    id: str
    connected: bool = False
    calibrated: bool = False
    fps: float | None = None


class HeartbeatIn(BaseModel):
    version: str | None = None
    mode: str | None = None
    engine: str | None = None
    calibration: str | None = None
    uptime_s: float | None = None
    active_game: bool = False
    cameras: list[CameraBeat] = Field(default_factory=list, max_length=8)


class GameReport(BaseModel):
    game_id: str = Field(..., max_length=32)
    mode: str = Field("unknown", max_length=32)
    status: str = "finished"
    players: int = Field(1, ge=1, le=16)
    darts: int = Field(0, ge=0)
    started_at: datetime
    finished_at: datetime | None = None


class GamesIn(BaseModel):
    games: list[GameReport] = Field(..., max_length=500)


def _data(m: BaseModel) -> dict[str, Any]:
    return m.model_dump(exclude_unset=True)


# ---------------------------------------------------------------------------- operator panel
router = APIRouter(prefix="/api/fleet", tags=["fleet"], dependencies=[Depends(deps.require_operator)])


@router.get("/dashboard")
def dashboard(f: FleetService = Depends(fleet)) -> dict:
    return f.dashboard()


@router.get("/venues")
def list_venues(include_inactive: bool = True, f: FleetService = Depends(fleet)) -> list[dict]:
    return f.list_venues(include_inactive)


@router.post("/venues", status_code=201)
def create_venue(body: VenueIn, f: FleetService = Depends(fleet)) -> dict:
    return _wrap(f.create_venue, _data(body))


@router.get("/venues/{venue_id}")
def get_venue(venue_id: str, f: FleetService = Depends(fleet)) -> dict:
    return _wrap(f.get_venue, venue_id)


@router.patch("/venues/{venue_id}")
def update_venue(venue_id: str, body: VenueIn, f: FleetService = Depends(fleet)) -> dict:
    return _wrap(f.update_venue, venue_id, _data(body))


@router.delete("/venues/{venue_id}", status_code=204)
def delete_venue(venue_id: str, f: FleetService = Depends(fleet)) -> None:
    _wrap(f.delete_venue, venue_id)


@router.get("/boards")
def list_boards(f: FleetService = Depends(fleet)) -> list[dict]:
    return f.list_boards()


@router.post("/boards", status_code=201)
def create_board(body: BoardIn, f: FleetService = Depends(fleet)) -> dict:
    return _wrap(f.create_board, _data(body))


@router.get("/boards/{board_id}")
def get_board(board_id: str, f: FleetService = Depends(fleet)) -> dict:
    return _wrap(f.get_board, board_id)


@router.patch("/boards/{board_id}")
def update_board(board_id: str, body: BoardIn, f: FleetService = Depends(fleet)) -> dict:
    return _wrap(f.update_board, board_id, _data(body))


@router.post("/boards/{board_id}/rotate-key")
def rotate_key(board_id: str, f: FleetService = Depends(fleet)) -> dict:
    return _wrap(f.rotate_key, board_id)


@router.delete("/boards/{board_id}", status_code=204)
def delete_board(board_id: str, f: FleetService = Depends(fleet)) -> None:
    _wrap(f.delete_board, board_id)


@router.get("/tickets")
def list_tickets(status: str | None = None, venue_id: str | None = None, board_id: str | None = None,
                 f: FleetService = Depends(fleet)) -> list[dict]:
    return f.list_tickets(status, venue_id, board_id)


@router.post("/tickets", status_code=201)
def create_ticket(body: TicketIn, f: FleetService = Depends(fleet)) -> dict:
    return _wrap(f.create_ticket, _data(body))


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, f: FleetService = Depends(fleet)) -> dict:
    return _wrap(f.get_ticket, ticket_id)


@router.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: int, body: TicketIn, f: FleetService = Depends(fleet)) -> dict:
    return _wrap(f.update_ticket, ticket_id, _data(body))


@router.post("/tickets/{ticket_id}/comments")
def add_comment(ticket_id: int, body: CommentIn, f: FleetService = Depends(fleet)) -> dict:
    return _wrap(f.add_comment, ticket_id, body.author, body.text)


@router.get("/stats")
def stats(date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"),
          venue_id: str | None = None, board_id: str | None = None, f: FleetService = Depends(fleet)) -> dict:
    return _wrap(f.stats, date_from, date_to, venue_id, board_id)


@router.get("/settlements")
def settlements(month: str | None = None, f: FleetService = Depends(fleet)) -> dict:
    return _wrap(f.settlement, month)


# ---------------------------------------------------------------------------- ingest (boards)
ingest = APIRouter(prefix="/api/fleet/ingest", tags=["fleet-ingest"])


def board_id(x_board_key: str | None = Header(None), f: FleetService = Depends(fleet)) -> str:
    try:
        return f.authenticate(x_board_key)
    except PermissionError as e:
        raise HTTPException(401, str(e)) from e


@ingest.post("/heartbeat")
def heartbeat(body: HeartbeatIn, bid: str = Depends(board_id), f: FleetService = Depends(fleet)) -> dict:
    return f.heartbeat(bid, body.model_dump(mode="json"))


@ingest.post("/games")
def games(body: GamesIn, bid: str = Depends(board_id), f: FleetService = Depends(fleet)) -> dict:
    return _wrap(f.ingest_games, bid, [g.model_dump() for g in body.games])
