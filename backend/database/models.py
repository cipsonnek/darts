"""Database schema (SQLAlchemy 2). SQLite for local use, PostgreSQL in production.

History is append-only where it matters: game actions, detections and corrections are
never rewritten. A correction is a new row that references what it corrects.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class Player(Base):
    __tablename__ = "players"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    color: Mapped[str] = mapped_column(String(16), default="#e8324a")
    avatar: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class Game(Base):
    __tablename__ = "games"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    mode: Mapped[str] = mapped_column(String(32))
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="created")  # created|running|paused|finished|abandoned
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    winner_player_id: Mapped[str | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    state_cache: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    players: Mapped[list["GamePlayer"]] = relationship(back_populates="game", order_by="GamePlayer.position",
                                                       cascade="all, delete-orphan")


class GamePlayer(Base):
    __tablename__ = "game_players"
    __table_args__ = (UniqueConstraint("game_id", "position"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"))
    position: Mapped[int] = mapped_column(Integer)
    game: Mapped[Game] = relationship(back_populates="players")
    player: Mapped[Player] = relationship()


class GameAction(Base):
    """Append-only action log of a game (see backend/game_engine/base.py::replay)."""

    __tablename__ = "game_actions"
    __table_args__ = (UniqueConstraint("game_id", "seq"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))  # dart|correct|void_dart|undo|next_turn
    sector: Mapped[int | None] = mapped_column(Integer, nullable=True)
    multiplier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dart_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    target_dart_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    player_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # vision|manual|auto
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Detection(Base):
    """Every dart the vision engine reported, with its full measurement payload."""

    __tablename__ = "detections"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    game_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    player_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sector: Mapped[int] = mapped_column(Integer)
    multiplier: Mapped[int] = mapped_column(Integer)
    score: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(8))
    x_mm: Mapped[float] = mapped_column(Float)
    y_mm: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    # accepted | pending | resolved | rejected | unassigned
    status: Mapped[str] = mapped_column(String(16), default="accepted", index=True)
    final_label: Mapped[str | None] = mapped_column(String(8), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Correction(Base):
    __tablename__ = "corrections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    detection_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    game_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    original_label: Mapped[str | None] = mapped_column(String(8), nullable=True)
    corrected_label: Mapped[str] = mapped_column(String(8))
    reason: Mapped[str] = mapped_column(String(32), default="manual")  # manual|uncertain_choice|void
    # Where the dart really was (optional, from a click on the board): used to evaluate
    # detection accuracy and calibration drift.
    x_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    y_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class CalibrationProfile(Base):
    __tablename__ = "calibration_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # intrinsics | pose | validation
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    grade: Mapped[str | None] = mapped_column(String(16), nullable=True)
    method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CameraSetting(Base):
    __tablename__ = "camera_settings"
    camera_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EventLog(Base):
    """Engine events other than darts (state changes, takeouts, obstructions, errors...)."""

    __tablename__ = "event_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
