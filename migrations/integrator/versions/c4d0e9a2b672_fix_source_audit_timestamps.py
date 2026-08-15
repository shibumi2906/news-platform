"""fix source audit timestamps

Revision ID: c4d0e9a2b672
Revises: c4d0e9a2b671
"""
import sqlalchemy as sa
from alembic import op

revision = "c4d0e9a2b672"
down_revision = "c4d0e9a2b671"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.alter_column("source_state_audit", "created_at", server_default=sa.text("now()"))
    op.alter_column("source_state_audit", "updated_at", server_default=sa.text("now()"))

def downgrade() -> None:
    op.alter_column("source_state_audit", "updated_at", server_default=None)
    op.alter_column("source_state_audit", "created_at", server_default=None)
