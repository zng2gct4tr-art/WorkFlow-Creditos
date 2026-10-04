from datetime import datetime, timezone
from uuid import uuid4
from decimal import Decimal
from sqlalchemy import (
    String,
    Text,
    ForeignKey,
    Numeric,
    DateTime,
    Date,
    Boolean,
    Integer,
    JSON,
    Index,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Entity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Role(Entity, Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    permissions: Mapped[list] = mapped_column(JSON, default=list)


class Permission(Base):
    __tablename__ = "permissions"
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    description: Mapped[str] = mapped_column(String(200))


class User(Entity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(Text)
    role_ids: Mapped[list] = mapped_column(JSON, default=list)
    client_id: Mapped[str | None] = mapped_column(
        ForeignKey("clients.id", use_alter=True, name="fk_user_client"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    branch: Mapped[str] = mapped_column(String(100), default="")
    supervisor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )


class Session(Entity, Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    csrf: Mapped[str] = mapped_column(String(128))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginAttempt(Entity, Base):
    __tablename__ = "login_attempts"
    key: Mapped[str] = mapped_column(String(64), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)


class PasswordReset(Entity, Base):
    __tablename__ = "password_resets"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Client(Entity, Base):
    __tablename__ = "clients"
    name: Mapped[str] = mapped_column(String(250))
    rut: Mapped[str] = mapped_column(String(12), unique=True)
    account_number: Mapped[str] = mapped_column(String(100), unique=True)
    manager_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", use_alter=True, name="fk_client_manager"), index=True
    )
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"))
    contact: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    phone: Mapped[str] = mapped_column(String(100), default="")
    address: Mapped[str] = mapped_column(String(500), default="")
    activity: Mapped[str] = mapped_column(String(200), default="")
    branch: Mapped[str] = mapped_column(String(100), default="")
    financials: Mapped[dict] = mapped_column(JSON, default=dict)
    guarantees: Mapped[str] = mapped_column(Text, default="")
    related_companies: Mapped[list] = mapped_column(JSON, default=list)
    guarantors: Mapped[list] = mapped_column(JSON, default=list)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ClientContact(Entity, Base):
    __tablename__ = "client_contacts"
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254))
    phone: Mapped[str] = mapped_column(String(100), default="")


class CompanyRelation(Entity, Base):
    __tablename__ = "company_relations"
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    related_client_id: Mapped[str | None] = mapped_column(
        ForeignKey("clients.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(250))
    kind: Mapped[str] = mapped_column(String(100))


class Product(Entity, Base):
    __tablename__ = "products"
    name: Mapped[str] = mapped_column(String(200), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Profile(Entity, Base):
    __tablename__ = "profiles"
    name: Mapped[str] = mapped_column(String(200), unique=True)
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ChecklistTemplate(Entity, Base):
    __tablename__ = "checklist_templates"
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), unique=True)
    name: Mapped[str] = mapped_column(String(200))


class ChecklistRequirement(Entity, Base):
    __tablename__ = "checklist_requirements"
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100), default="General")
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    validity_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Proposal(Entity, Base):
    __tablename__ = "proposals"
    __table_args__ = (
        CheckConstraint("amount > 0"),
        CheckConstraint("term_months > 0"),
        Index(
            "uq_active_client",
            "client_id",
            unique=True,
            postgresql_where=__import__("sqlalchemy").text(
                "state NOT IN ('approved','rejected','cancelled')"
            ),
        ),
    )
    code: Mapped[str] = mapped_column(String(30), unique=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    currency: Mapped[str] = mapped_column(String(3), default="UYU")
    term_months: Mapped[int] = mapped_column(Integer)
    rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    purpose: Mapped[str] = mapped_column(Text)
    guarantees: Mapped[str] = mapped_column(Text, default="")
    payment_method: Mapped[str] = mapped_column(Text, default="")
    observations: Mapped[str] = mapped_column(Text, default="")
    participants: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    cycle: Mapped[int] = mapped_column(Integer, default=1)
    extra_requests: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProposalVersion(Entity, Base):
    __tablename__ = "proposal_versions"
    __table_args__ = (UniqueConstraint("proposal_id", "version"),)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    snapshot: Mapped[dict] = mapped_column(JSON)


class ProposalRequirement(Entity, Base):
    __tablename__ = "proposal_requirements"
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), index=True)
    template_id: Mapped[str | None] = mapped_column(
        ForeignKey("checklist_requirements.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100))
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    validity_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    additional: Mapped[bool] = mapped_column(Boolean, default=False)
    client_visible: Mapped[bool] = mapped_column(Boolean, default=True)


class Document(Entity, Base):
    __tablename__ = "documents"
    requirement_id: Mapped[str] = mapped_column(
        ForeignKey("proposal_requirements.id"), index=True
    )
    uploader_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="uploaded")
    observations: Mapped[str] = mapped_column(Text, default="")
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    extraction: Mapped[dict] = mapped_column(JSON, default=dict)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class DocumentValidation(Entity, Base):
    __tablename__ = "document_validations"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    automatic: Mapped[bool] = mapped_column(Boolean)
    previous_status: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)


class AIValidation(Entity, Base):
    __tablename__ = "ai_validations"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    provider: Mapped[str] = mapped_column(String(100))
    result: Mapped[dict] = mapped_column(JSON)


class AnalystAssignment(Entity, Base):
    __tablename__ = "analyst_assignments"
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    assigned_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CreditDecision(Entity, Base):
    __tablename__ = "credit_decisions"
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), index=True)
    analyst_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(30))
    justification: Mapped[str] = mapped_column(Text)
    considered_version: Mapped[int] = mapped_column(Integer)
    participants: Mapped[list] = mapped_column(JSON, default=list)


class InformationRequest(Entity, Base):
    __tablename__ = "information_requests"
    __table_args__ = (UniqueConstraint("proposal_id", "cycle"),)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"))
    cycle: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    client_visible: Mapped[bool] = mapped_column(Boolean, default=True)


class Comment(Entity, Base):
    __tablename__ = "comments"
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Attachment(Entity, Base):
    __tablename__ = "attachments"
    comment_id: Mapped[str] = mapped_column(ForeignKey("comments.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))


class SLARecord(Entity, Base):
    __tablename__ = "sla_records"
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), index=True)
    area: Mapped[str] = mapped_column(String(30))
    cycle: Mapped[int] = mapped_column(Integer)
    allowance: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    alerted: Mapped[str] = mapped_column(String(20), default="")


class SLAEvent(Entity, Base):
    __tablename__ = "sla_events"
    sla_id: Mapped[str] = mapped_column(ForeignKey("sla_records.id"))
    action: Mapped[str] = mapped_column(String(30))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Notification(Entity, Base):
    __tablename__ = "notifications"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    proposal_id: Mapped[str | None] = mapped_column(
        ForeignKey("proposals.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    email_status: Mapped[str] = mapped_column(String(30), default="pending")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource: Mapped[str] = mapped_column(String(100), index=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str] = mapped_column(String(100), default="")
    session_id: Mapped[str] = mapped_column(String(64), default="")
    previous_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class Holiday(Base):
    __tablename__ = "holidays"
    date: Mapped[__import__("datetime").date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))


class CommercialReport(Entity, Base):
    __tablename__ = "commercial_reports"
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), unique=True)
    content: Mapped[str] = mapped_column(Text, default="")
    ai_content: Mapped[str] = mapped_column(Text, default="")
    ai_assessment: Mapped[dict] = mapped_column(JSON, default=dict)
    human_assessment: Mapped[dict] = mapped_column(JSON, default=dict)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    final: Mapped[bool] = mapped_column(Boolean, default=False)


class CommercialReportVersion(Entity, Base):
    __tablename__ = "commercial_report_versions"
    report_id: Mapped[str] = mapped_column(
        ForeignKey("commercial_reports.id"), index=True
    )
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(String(30))
    final: Mapped[bool] = mapped_column(Boolean, default=False)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
