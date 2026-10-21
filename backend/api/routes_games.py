"""Players, games, statistics."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api import deps
from backend.api.schemas import CorrectionIn, DartIn, GameIn, PlayerIn, PlayerPatch
from backend.game_engine import GameError

router = APIRouter(prefix="/api", tags=["games"])


def _wrap(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except KeyError as exc:
        raise HTTPException(404, f"not found: {exc}") from exc
    except GameError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/game-modes")
def modes(games=Depends(deps.games)) -> list[dict]:
    return games.modes()


# ---------------------------------------------------------------------------- players
@router.get("/players")
def players(include_archived: bool = False, games=Depends(deps.games)) -> list[dict]:
    return games.list_players(include_archived)


@router.post("/players", status_code=201)
def create_player(body: PlayerIn, games=Depends(deps.games)) -> dict:
    return _wrap(games.create_player, body.name, body.nickname, body.color, body.avatar)


@router.get("/players/{player_id}")
def get_player(player_id: str, games=Depends(deps.games)) -> dict:
    return _wrap(games.get_player, player_id)


@router.patch("/players/{player_id}")
def patch_player(player_id: str, body: PlayerPatch, games=Depends(deps.games)) -> dict:
    return _wrap(games.update_player, player_id, **body.model_dump(exclude_none=True))


# ---------------------------------------------------------------------------- games
@router.get("/games")
def list_games(status: str | None = Query(None, pattern="^(created|running|paused|finished|abandoned)$"),
               limit: int = Query(50, ge=1, le=500), games=Depends(deps.games)) -> list[dict]:
    return games.list_games(status, limit)


@router.post("/games", status_code=201)
def create_game(body: GameIn, games=Depends(deps.games)) -> dict:
    try:
        return _wrap(games.create_game, body.mode, body.settings, body.player_ids, body.start)
    except HTTPException as exc:
        # Unknown mode or invalid rules are bad input, not a conflict with the current state.
        if exc.status_code == 409:
            raise HTTPException(422, exc.detail) from exc
        raise


@router.get("/games/active")
def active_game(games=Depends(deps.games)) -> dict | None:
    gid = games.active_game_id()
    return games.get_game(gid) if gid else None


@router.get("/games/{game_id}")
def get_game(game_id: str, games=Depends(deps.games)) -> dict:
    return _wrap(games.get_game, game_id)


@router.post("/games/{game_id}/start")
def start(game_id: str, games=Depends(deps.games)) -> dict:
    return _wrap(games.set_status, game_id, "running")


@router.post("/games/{game_id}/resume")
def resume(game_id: str, games=Depends(deps.games)) -> dict:
    return _wrap(games.set_status, game_id, "running")


@router.post("/games/{game_id}/pause")
def pause(game_id: str, games=Depends(deps.games)) -> dict:
    return _wrap(games.set_status, game_id, "paused")


@router.post("/games/{game_id}/finish")
def finish(game_id: str, games=Depends(deps.games)) -> dict:
    return _wrap(games.set_status, game_id, "finished")


@router.post("/games/{game_id}/abandon")
def abandon(game_id: str, games=Depends(deps.games)) -> dict:
    return _wrap(games.set_status, game_id, "abandoned")


@router.delete("/games/{game_id}", dependencies=[Depends(deps.require_admin)], status_code=204)
def delete(game_id: str, games=Depends(deps.games)) -> None:
    _wrap(games.delete_game, game_id)


@router.post("/games/{game_id}/darts")
def throw(game_id: str, body: DartIn, games=Depends(deps.games)) -> dict:
    return _wrap(games.throw, game_id, body.label, "manual")


@router.post("/games/{game_id}/undo")
def undo(game_id: str, games=Depends(deps.games)) -> dict:
    return _wrap(games.undo, game_id)


@router.post("/games/{game_id}/next-turn")
def next_turn(game_id: str, games=Depends(deps.games)) -> dict:
    return _wrap(games.next_turn, game_id)


@router.post("/games/{game_id}/corrections")
def correct(game_id: str, body: CorrectionIn, games=Depends(deps.games)) -> dict:
    return _wrap(games.correct, game_id, body.dart_id, body.label, body.x_mm, body.y_mm, body.note)


# ---------------------------------------------------------------------------- statistics
@router.get("/stats/overview")
def stats_overview(stats=Depends(deps.stats)) -> dict[str, Any]:
    return stats.overview()


@router.get("/stats/players/{player_id}")
def player_stats(player_id: str, mode: str | None = Query(None, max_length=32),
                 last: int | None = Query(None, ge=1, le=1000), stats=Depends(deps.stats)) -> dict:
    return _wrap(stats.player_stats, player_id, mode, last)


@router.get("/stats/heatmap")
def heatmap(player_id: str | None = None, limit: int = Query(5000, ge=1, le=50000), stats=Depends(deps.stats)) -> list[dict]:
    return stats.heatmap(player_id, limit)
