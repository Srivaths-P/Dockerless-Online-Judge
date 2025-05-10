"""create initial tables

Revision ID: 3e77604f7568
Revises: 
Create Date: 2025-05-09 21:24:23.069634

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = '3e77604f7568'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
