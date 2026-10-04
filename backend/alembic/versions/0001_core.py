"""Initial banking workflow schema with append-only audit protection."""

from alembic import op
from app.db import Base
from app import models

revision = "0001_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(op.get_bind())
    op.execute("CREATE SEQUENCE IF NOT EXISTS credit_proposal_number START 1")
    op.execute("""CREATE FUNCTION deny_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Audit events are append-only'; END; $$""")
    op.execute(
        "CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_events FOR EACH STATEMENT EXECUTE FUNCTION deny_audit_mutation()"
    )


def downgrade():
    raise RuntimeError(
        "Destructive downgrade prohibited: restore a verified backup through change control."
    )
