"""Separate private risk requests from client-visible requirements."""

from alembic import op
from sqlalchemy import inspect, Column, Boolean, text

revision = "0002_requirement_visibility"
down_revision = "0001_core"
branch_labels = None
depends_on = None


def upgrade():
    if "client_visible" not in {
        c["name"] for c in inspect(op.get_bind()).get_columns("proposal_requirements")
    }:
        op.add_column(
            "proposal_requirements",
            Column(
                "client_visible", Boolean(), nullable=False, server_default=text("true")
            ),
        )


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade.")
