"""drop users.phone

RideMatch no longer collects a phone number (CONTRACT.md D22). Matches contracts/schema.sql.

Revision ID: 0002_drop_users_phone
Revises: 0001_initial
Create Date: 2026-10-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_drop_users_phone"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS phone")


def downgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN phone varchar(20)")
