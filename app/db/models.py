"""ROMKA data model. Every row carrying personal data is scoped by user_id.

See docs/ARCHITECTURE.md and docs/DATA-PRIVACY.md for the rationale.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utcnow


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), default="fa", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Tehran", nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="owner", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    profile: Mapped["UserProfile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # Minutes from midnight — timezone-independent inside the planning engine.
    wake_time: Mapped[int] = mapped_column(Integer, default=420, nullable=False)
    sleep_time: Mapped[int] = mapped_column(Integer, default=1380, nullable=False)
    work_start: Mapped[int] = mapped_column(Integer, default=540, nullable=False)
    work_end: Mapped[int] = mapped_column(Integer, default=1080, nullable=False)
    commute_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    meal_windows: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    focus_peak_start: Mapped[int] = mapped_column(Integer, default=480, nullable=False)
    focus_peak_end: Mapped[int] = mapped_column(Integer, default=660, nullable=False)
    daily_focus_capacity_min: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    buffer_pct: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    energy_drains: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    energy_boosters: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    health_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="profile")


class Goal(Base, TimestampMixin):
    __tablename__ = "goals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    horizon: Mapped[str] = mapped_column(String(20), default="weekly", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    success_metric: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    target_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    goal_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    success_metrics: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    blockers: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    decisions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    # duration_min is the ESTIMATE and is never overwritten by reality;
    # actual_min is what really happened (used for calibration).
    duration_min: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    actual_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1 = highest
    energy: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="focus", nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    earliest_start_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latest_end_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    depends_on: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    must_do: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deferrable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recurrence_rule: Mapped[str | None] = mapped_column(String(200), nullable=True)  # RFC 5545 RRULE
    status: Mapped[str] = mapped_column(String(20), default="todo", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_for: Mapped[datetime | None] = mapped_column(Date, nullable=True)


class FixedEvent(Base, TimestampMixin):
    __tablename__ = "fixed_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    date: Mapped[datetime] = mapped_column(Date, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    start_min: Mapped[int] = mapped_column(Integer, nullable=False)
    end_min: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(20), default="meeting", nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    date: Mapped[datetime] = mapped_column(Date, index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    energy_mode: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    blocks: Mapped[list["PlanBlock"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class PlanBlock(Base):
    __tablename__ = "plan_blocks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True, nullable=False)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    start_min: Mapped[int] = mapped_column(Integer, nullable=False)
    end_min: Mapped[int] = mapped_column(Integer, nullable=False)
    block_type: Mapped[str] = mapped_column(String(20), default="task", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="planned", nullable=False)
    plan: Mapped["Plan"] = relationship(back_populates="blocks")


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="گفتوگو با رومکا", nullable=False)


class Message(Base, TimestampMixin):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    active_agent_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    sources: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    warnings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class MemoryItem(Base, TimestampMixin):
    __tablename__ = "memory_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    layer: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="user", nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), default="verified", nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(20), default="personal", nullable=False)
    agent_scope: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # [] = shared
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_id: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    output: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    verdict: Mapped[str] = mapped_column(String(30), default="accepted", nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ActionRecord(Base, TimestampMixin):
    __tablename__ = "action_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    requester: Mapped[str] = mapped_column(String(60), nullable=False)
    goal: Mapped[str] = mapped_column(String(400), nullable=False)
    tool: Mapped[str] = mapped_column(String(60), nullable=False)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending_approval", nullable=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), default="", index=True, nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIUsage(Base, TimestampMixin):
    __tablename__ = "ai_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)


class SecurityEvent(Base, TimestampMixin):
    __tablename__ = "security_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default="web", nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ip: Mapped[str] = mapped_column(String(64), default="", nullable=False)


class Setting(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_settings_user_key"),)


class ChannelIdentity(Base, TimestampMixin):
    __tablename__ = "channel_identities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("channel", "external_id", name="uq_channel_external"),)


class Skill(Base, TimestampMixin):
    __tablename__ = "skills"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(String(60), default="general", nullable=False)
    source_url: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    source_commit: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    license_spdx: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    version: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    required_permissions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="discovered", nullable=False)
    score: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    evaluation_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    test_result: Mapped[str] = mapped_column(Text, default="", nullable=False)
    previous_version: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class SkillUsage(Base, TimestampMixin):
    __tablename__ = "skill_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)


class FitnessProfile(Base):
    __tablename__ = "fitness_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    goal: Mapped[str] = mapped_column(String(30), default="maintain", nullable=False)
    sex: Mapped[str] = mapped_column(String(20), default="unspecified", nullable=False)
    activity: Mapped[str] = mapped_column(String(20), default="moderate", nullable=False)
    experience: Mapped[str] = mapped_column(String(30), default="beginner", nullable=False)
    days_per_week: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    session_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    equipment: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    injuries: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    food_preferences: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    allergies: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    food_budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class WorkoutLog(Base, TimestampMixin):
    __tablename__ = "workout_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    date: Mapped[datetime] = mapped_column(Date, index=True, nullable=False)
    exercise: Mapped[str] = mapped_column(String(200), nullable=False)
    sets: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rpe: Mapped[int] = mapped_column(Integer, default=7, nullable=False)  # rate of perceived exertion 1-10
    pain_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
