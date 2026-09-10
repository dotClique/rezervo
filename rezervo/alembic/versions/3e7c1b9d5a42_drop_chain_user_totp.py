"""drop_chain_user_totp

Revision ID: 3e7c1b9d5a42
Revises: ccf2b2be66fc
Create Date: 2026-09-10 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "3e7c1b9d5a42"
down_revision = "ccf2b2be66fc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("chain_users", "totp")


def downgrade() -> None:
    op.add_column("chain_users", sa.Column("totp", sa.String(), nullable=True))
