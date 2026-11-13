"""Record successful downstream feed requests."""

import sqlalchemy as sa
from alembic import op

revision = "2c64f8ad510"
down_revision = "a6c1e9f42b30"


def upgrade() -> None:
    op.add_column(
        "site_connection",
        sa.Column("delivery_mode", sa.String(16), nullable=False, server_default="push"),
    )
    op.add_column("site_connection", sa.Column("last_pull_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("site_connection", "last_pull_at")
    op.drop_column("site_connection", "delivery_mode")
