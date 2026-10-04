from decimal import Decimal
from datetime import datetime, date
from sqlalchemy import select, or_
from fastapi import HTTPException
from .models import *
from .security import permissions, require
from .sla import start_sla, finish_sla, sla_view, active_sla
from .audit import record

TERMINAL = {"approved", "rejected", "cancelled"}
EDITABLE = {"draft", "documentation_pending", "ready"}


def serial(obj, exclude=()):
    out = {}
    for c in obj.__table__.columns:
        if c.name in exclude:
            continue
        val = getattr(obj, c.name)
        out[c.name] = (
            val.isoformat()
            if isinstance(val, (datetime, date))
            else str(val)
            if isinstance(val, Decimal)
            else val
        )
    return out


def client_access(db, u, c):
    if not c or c.deleted:
        raise HTTPException(404, "Empresa no encontrada.")
    perms = permissions(db, u)
    require(db, u, "client.view")
    if u.client_id:
        if u.client_id != c.id:
            raise HTTPException(404, "Empresa no encontrada.")
    elif "portfolio.all" in perms:
        pass
    elif c.manager_id == u.id:
        pass
    elif "team.view" in perms and db.get(User, c.manager_id).supervisor_id == u.id:
        pass
    elif "risk.view" in perms:
        assigned = db.scalar(
            select(AnalystAssignment)
            .join(Proposal, Proposal.id == AnalystAssignment.proposal_id)
            .where(
                Proposal.client_id == c.id,
                AnalystAssignment.user_id == u.id,
                AnalystAssignment.active.is_(True),
            )
        )
        if not assigned:
            raise HTTPException(404, "Empresa no encontrada.")
    else:
        raise HTTPException(404, "Empresa no encontrada.")
    return c


def scoped_clients(db, u):
    require(db, u, "client.view")
    q = select(Client).where(Client.deleted.is_(False))
    perms = permissions(db, u)
    if u.client_id:
        q = q.where(Client.id == u.client_id)
    elif "portfolio.all" in perms:
        pass
    else:
        terms = [Client.manager_id == u.id]
        if "team.view" in perms:
            terms.append(
                Client.manager_id.in_(select(User.id).where(User.supervisor_id == u.id))
            )
        if "risk.view" in perms:
            terms.append(
                Client.id.in_(
                    select(Proposal.client_id)
                    .join(
                        AnalystAssignment, AnalystAssignment.proposal_id == Proposal.id
                    )
                    .where(
                        AnalystAssignment.user_id == u.id,
                        AnalystAssignment.active.is_(True),
                    )
                )
            )
        q = q.where(or_(*terms))
    return q


def proposal_access(db, u, pid, lock=False):
    p = (
        db.scalar(select(Proposal).where(Proposal.id == pid).with_for_update())
        if lock
        else db.get(Proposal, pid)
    )
    if not p:
        raise HTTPException(404, "Propuesta no encontrada.")
    c = client_access(db, u, db.get(Client, p.client_id))
    perms = permissions(db, u)
    if not u.client_id and "portfolio.all" not in perms and c.manager_id != u.id:
        team = "team.view" in perms and db.get(User, c.manager_id).supervisor_id == u.id
        assigned = db.scalar(
            select(AnalystAssignment.id).where(
                AnalystAssignment.proposal_id == p.id,
                AnalystAssignment.user_id == u.id,
                AnalystAssignment.active.is_(True),
            )
        )
        if not team and not assigned:
            raise HTTPException(404, "Propuesta no encontrada.")
    return p


def check_manager(db, u, p):
    c = db.get(Client, p.client_id)
    if u.client_id or (
        c.manager_id != u.id and "portfolio.all" not in permissions(db, u)
    ):
        raise HTTPException(403, "La propuesta corresponde a otro gestor.")


def check_analyst(db, u, p):
    if u.client_id:
        raise HTTPException(403, "Acción interna.")
    if not db.scalar(
        select(AnalystAssignment).where(
            AnalystAssignment.proposal_id == p.id,
            AnalystAssignment.user_id == u.id,
            AnalystAssignment.active.is_(True),
        )
    ):
        raise HTTPException(
            403, "Debe estar asignado al expediente para tomar una decisión."
        )


def requirement_status(db, r):
    docs = list(
        db.scalars(
            select(Document).where(
                Document.requirement_id == r.id, Document.deleted.is_(False)
            )
        )
    )
    if not docs:
        return "pending"
    if any(d.expires_at and d.expires_at <= now() for d in docs):
        return "expired"
    if any(d.status == "incorrect" for d in docs):
        return "incorrect"
    if all(d.status == "correct" for d in docs):
        return "correct"
    if any(d.status == "processing" for d in docs):
        return "validating"
    return "uploaded"


def completeness(db, p):
    reqs = list(
        db.scalars(
            select(ProposalRequirement).where(
                ProposalRequirement.proposal_id == p.id,
                ProposalRequirement.mandatory.is_(True),
            )
        )
    )
    received = sum(1 for r in reqs if requirement_status(db, r) != "pending")
    valid = bool(reqs) and all(requirement_status(db, r) == "correct" for r in reqs)
    return round(received / max(1, len(reqs)) * 100), valid


def document_ready(db, p, actor=None):
    pct, valid = completeness(db, p)
    if pct == 100 and valid and p.state in EDITABLE:
        if not active_sla(db, p, "commercial"):
            start_sla(db, p, "commercial", actor)
        notify(
            db,
            p,
            "Documentación completa",
            "La documentación está completa y validada. Prepare el informe comercial.",
        )


def snapshot(db, p, u, request=None, action="proposal.update"):
    db.flush()
    data = serial(p)
    db.add(
        ProposalVersion(
            proposal_id=p.id, version=p.version, actor_id=u.id, snapshot=data
        )
    )
    record(db, u, action, p.id, after=data, request=request)


def notify(db, p, title, body, client_visible=True, extra_users=(), client_body=None):
    c = db.get(Client, p.client_id)
    ids = {c.manager_id, *extra_users}
    ids.update(
        db.scalars(
            select(AnalystAssignment.user_id).where(
                AnalystAssignment.proposal_id == p.id,
                AnalystAssignment.active.is_(True),
            )
        )
    )
    if client_visible:
        ids.update(
            db.scalars(
                select(User.id).where(User.client_id == c.id, User.active.is_(True))
            )
        )
    for user_id in ids:
        recipient = db.get(User, user_id)
        message = (
            client_body if recipient.client_id and client_body is not None else body
        )
        db.add(
            Notification(user_id=user_id, proposal_id=p.id, title=title, body=message)
        )


def transition(db, u, p, body, request):
    if p.version != body.version:
        raise HTTPException(409, "La propuesta cambió. Actualice antes de continuar.")
    action = body.action
    expected = {
        "prepare": {"draft", "documentation_pending"},
        "submit": {"draft", "documentation_pending", "ready"},
        "request_information": {"in_analysis", "reanalysis"},
        "resubmit": {"additional_requested"},
        "approve": {"in_analysis", "reanalysis"},
        "reject": {"in_analysis", "reanalysis"},
        "cancel": set(EDITABLE) | {"in_analysis", "reanalysis", "additional_requested"},
        "reopen": {"rejected"},
    }
    if action not in expected or p.state not in expected[action]:
        raise HTTPException(409, "Esta acción no está disponible en la etapa actual.")
    perm = {
        "prepare": "proposal.edit",
        "submit": "proposal.submit",
        "resubmit": "proposal.submit",
        "request_information": "risk.request",
        "approve": "risk.approve",
        "reject": "risk.reject",
        "cancel": "proposal.cancel",
        "reopen": "proposal.reopen",
    }[action]
    require(db, u, perm)
    if action in {"approve", "reject", "request_information"}:
        check_analyst(db, u, p)
    else:
        check_manager(db, u, p)
    if (
        action in {"approve", "reject", "request_information", "reopen", "cancel"}
        and len(body.reason.strip()) < 3
    ):
        raise HTTPException(
            422, "Indique un motivo o justificación de al menos tres caracteres."
        )
    before = serial(p)
    if action in {"prepare", "submit", "resubmit", "approve"}:
        pct, valid = completeness(db, p)
        if pct != 100 or not valid:
            raise HTTPException(
                409,
                "La documentación debe estar completa y validada antes de continuar.",
            )
    if action == "prepare":
        document_ready(db, p, u)
        p.state = "ready"
    elif action == "submit":
        report = db.scalar(
            select(CommercialReport).where(CommercialReport.proposal_id == p.id)
        )
        if not report or not report.final or not report.content.strip():
            raise HTTPException(
                409, "Finalice el informe comercial antes de enviar a Riesgos."
            )
        document_ready(db, p, u)
        finish_sla(db, p, "commercial", u)
        start_sla(db, p, "risk", u)
        p.state = "in_analysis"
    elif action == "request_information":
        if p.extra_requests >= 1:
            raise HTTPException(
                409,
                "Ya se realizó la única solicitud formal de información adicional de este ciclo.",
            )
        names = body.requirements or [body.reason]
        for name in names:
            if not name.strip():
                raise HTTPException(422, "El requisito adicional necesita un nombre.")
            db.add(
                ProposalRequirement(
                    proposal_id=p.id,
                    name=name[:200],
                    category="Información adicional",
                    mandatory=True,
                    additional=True,
                    client_visible=body.client_visible,
                    rules={},
                )
            )
        db.add(
            InformationRequest(
                proposal_id=p.id,
                cycle=p.cycle,
                actor_id=u.id,
                reason=body.reason,
                client_visible=body.client_visible,
            )
        )
        finish_sla(db, p, "risk", u, pause=True)
        p.extra_requests = 1
        p.state = "additional_requested"
    elif action == "resubmit":
        finish_sla(db, p, "risk", u)
        start_sla(db, p, "risk", u)
        p.state = "reanalysis"
        record(db, u, "sla.restart", p.id, after={"cycle": p.cycle}, request=request)
    elif action in {"approve", "reject"}:
        decision = "approved" if action == "approve" else "rejected"
        ids = list(
            db.scalars(
                select(AnalystAssignment.user_id).where(
                    AnalystAssignment.proposal_id == p.id,
                    AnalystAssignment.active.is_(True),
                )
            )
        )
        db.add(
            CreditDecision(
                proposal_id=p.id,
                analyst_id=u.id,
                decision=decision,
                justification=body.reason,
                considered_version=p.version,
                participants=ids,
            )
        )
        finish_sla(db, p, "risk", u)
        p.state = decision
    elif action == "cancel":
        finish_sla(db, p, "commercial", u)
        finish_sla(db, p, "risk", u)
        p.state = "cancelled"
    elif action == "reopen":
        c = db.scalar(select(Client).where(Client.id == p.client_id).with_for_update())
        other = db.scalar(
            select(Proposal).where(
                Proposal.client_id == c.id,
                Proposal.id != p.id,
                Proposal.state.not_in(TERMINAL),
            )
        )
        if other:
            raise HTTPException(409, "La empresa ya tiene otra propuesta activa.")
        p.cycle += 1
        p.extra_requests = 0
        p.state = "documentation_pending"
    p.version += 1
    p.updated_at = now()
    snapshot(db, p, u, request, "proposal." + action)
    record(
        db,
        u,
        "workflow.transition",
        p.id,
        before=before,
        after={"state": p.state, "reason": body.reason, "version": p.version},
        request=request,
    )
    notify(
        db,
        p,
        {
            "submit": "Expediente enviado a Riesgos",
            "resubmit": "Expediente devuelto a Riesgos",
            "approve": "Propuesta aprobada",
            "reject": "Propuesta rechazada",
            "cancel": "Propuesta cancelada",
            "reopen": "Propuesta reabierta",
            "request_information": "Información adicional solicitada",
            "prepare": "Lista para enviar",
        }[action],
        body.reason or "La solicitud cambió de etapa.",
        client_visible=body.client_visible if action == "request_information" else True,
        client_body=body.reason
        if action == "request_information"
        else "La solicitud cambió de etapa. Consulte el portal para conocer el estado general.",
    )
    return p


def proposal_dict(db, p, u):
    c = db.get(Client, p.client_id)
    prod = db.get(Product, p.product_id)
    data = serial(p)
    data.update(client_name=c.name, product_name=prod.name)
    data["requirements"] = []
    for r in db.scalars(
        select(ProposalRequirement)
        .where(ProposalRequirement.proposal_id == p.id)
        .order_by(ProposalRequirement.created_at)
    ):
        if u.client_id and not r.client_visible:
            continue
        item = serial(r)
        item["status"] = requirement_status(db, r)
        item["documents"] = []
        for d in db.scalars(
            select(Document).where(
                Document.requirement_id == r.id, Document.deleted.is_(False)
            )
        ):
            doc = serial(d, exclude=("storage_key",))
            if u.client_id:
                doc.pop("extraction", None)
                doc.pop("uploader_id", None)
            item["documents"].append(doc)
        data["requirements"].append(item)
    pct, valid = completeness(db, p)
    data["completeness"] = pct
    data["validity"] = valid
    data["sla"] = {}
    for s in db.scalars(
        select(SLARecord)
        .where(SLARecord.proposal_id == p.id)
        .order_by(SLARecord.created_at)
    ):
        data["sla"][s.area] = sla_view(db, s)
    if u.client_id:
        data = {
            k: v
            for k, v in data.items()
            if k
            in {
                "id",
                "code",
                "client_id",
                "client_name",
                "product_name",
                "amount",
                "currency",
                "term_months",
                "state",
                "requirements",
                "completeness",
                "validity",
                "sla",
                "created_at",
                "updated_at",
            }
        }
    else:
        report = db.scalar(
            select(CommercialReport).where(CommercialReport.proposal_id == p.id)
        )
        data["report"] = serial(report) if report else None
        data["assignments"] = [
            {"user_id": a.user_id, "name": db.get(User, a.user_id).name}
            for a in db.scalars(
                select(AnalystAssignment).where(
                    AnalystAssignment.proposal_id == p.id,
                    AnalystAssignment.active.is_(True),
                )
            )
        ]
    return data


def scoped_proposals(db, u):
    perms = permissions(db, u)
    ids = scoped_clients(db, u).with_only_columns(Client.id)
    q = select(Proposal).where(Proposal.client_id.in_(ids))
    if u.client_id or "portfolio.all" in perms:
        return q
    allowed = [
        Proposal.client_id.in_(select(Client.id).where(Client.manager_id == u.id))
    ]
    if "team.view" in perms:
        allowed.append(
            Proposal.client_id.in_(
                select(Client.id)
                .join(User, User.id == Client.manager_id)
                .where(User.supervisor_id == u.id)
            )
        )
    if "risk.view" in perms:
        allowed.append(
            Proposal.id.in_(
                select(AnalystAssignment.proposal_id).where(
                    AnalystAssignment.user_id == u.id,
                    AnalystAssignment.active.is_(True),
                )
            )
        )
    return q.where(or_(*allowed))
