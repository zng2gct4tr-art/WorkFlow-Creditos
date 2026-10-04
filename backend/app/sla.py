from datetime import timedelta, datetime, time
from zoneinfo import ZoneInfo
from sqlalchemy import select
from .models import Holiday, SLARecord, SLAEvent, now

TZ = ZoneInfo("America/Montevideo")


def business_days(start, end, holidays):
    """Fractional calendar business days, with full 24 hours counting as one weekday.
    Starts at the exact timestamp; weekends and configured holidays contribute zero.
    """
    if end <= start:
        return 0.0
    start, end = start.astimezone(TZ), end.astimezone(TZ)
    day = start.date()
    result = 0.0
    while day <= end.date():
        if day.weekday() < 5 and day not in holidays:
            low = max(start, datetime.combine(day, time.min, tzinfo=TZ))
            high = min(
                end, datetime.combine(day + timedelta(days=1), time.min, tzinfo=TZ)
            )
            result += max(0, (high - low).total_seconds()) / 86400
        day += timedelta(days=1)
    return round(result, 6)


def sla_view(db, s):
    holidays = set(db.scalars(select(Holiday.date)))
    consumed = business_days(s.started_at, s.paused_at or s.ended_at or now(), holidays)
    remaining = max(0, s.allowance - consumed)
    return dict(
        id=s.id,
        area=s.area,
        started_at=s.started_at.isoformat(),
        ended_at=s.ended_at.isoformat() if s.ended_at else None,
        paused=bool(s.paused_at and not s.ended_at),
        allowance=s.allowance,
        consumed=round(consumed, 2),
        remaining=round(remaining, 2),
        percent=round(consumed / s.allowance * 100, 2),
        breached=consumed > s.allowance,
        color="red"
        if consumed > s.allowance
        else "yellow"
        if remaining <= 1
        else "green",
        cycle=s.cycle,
    )


def start_sla(db, p, area, actor=None):
    from .models import Setting
    from .audit import record

    setting = db.get(Setting, "sla")
    allowance = (setting.value if setting else {}).get(
        area, 7 if area == "commercial" else 15
    )
    s = SLARecord(proposal_id=p.id, area=area, cycle=p.cycle, allowance=allowance)
    db.add(s)
    db.flush()
    db.add(SLAEvent(sla_id=s.id, action="start", actor_id=getattr(actor, "id", None)))
    record(
        db,
        actor,
        "sla.start",
        s.id,
        after={"proposal_id": p.id, "area": area, "allowance": allowance},
    )
    return s


def active_sla(db, p, area):
    return db.scalar(
        select(SLARecord)
        .where(
            SLARecord.proposal_id == p.id,
            SLARecord.area == area,
            SLARecord.ended_at.is_(None),
        )
        .order_by(SLARecord.created_at.desc())
        .limit(1)
    )


def finish_sla(db, p, area, actor, pause=False):
    from .audit import record

    s = active_sla(db, p, area)
    if s:
        if pause:
            s.paused_at = now()
        else:
            s.ended_at = now()
        db.add(
            SLAEvent(sla_id=s.id, action="pause" if pause else "end", actor_id=actor.id)
        )
        record(
            db, actor, "sla.pause" if pause else "sla.end", s.id, after=sla_view(db, s)
        )
