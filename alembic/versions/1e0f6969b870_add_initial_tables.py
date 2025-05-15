"""create initial tables

Revision ID: 86efb0f4237d # Keeping the original ID, assumes this is the replacement first script
Revises:
Create Date: 2025-05-13 00:51:17.774031 # Keeping original date

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '86efb0f4237d'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('email', sa.String(), nullable=False),
                    sa.Column('hashed_password', sa.String(), nullable=False),
                    sa.Column('is_active', sa.Boolean(), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
                    # Added rate limit columns
                    sa.Column('last_submission_at', sa.DateTime(timezone=True), nullable=True),
                    sa.Column('last_generation_at', sa.DateTime(timezone=True), nullable=True),
                    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
                    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_table('submissions',
                    sa.Column('id', sa.String(), nullable=False),
                    sa.Column('problem_id', sa.String(), nullable=False),
                    sa.Column('contest_id', sa.String(), nullable=False),
                    sa.Column('language', sa.String(), nullable=False),
                    sa.Column('code', sa.Text(), nullable=False),
                    sa.Column('submitter_id', sa.Integer(), nullable=False),
                    sa.Column('status', sa.String(), nullable=False),
                    sa.Column('results_json', sa.Text(), nullable=True),
                    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
                    sa.ForeignKeyConstraint(['submitter_id'], ['users.id'],
                                            name=op.f('fk_submissions_submitter_id_users')),
                    sa.PrimaryKeyConstraint('id', name=op.f('pk_submissions'))
                    )
    op.create_index(op.f('ix_submissions_contest_id'), 'submissions', ['contest_id'], unique=False)
    op.create_index(op.f('ix_submissions_id'), 'submissions', ['id'], unique=False)
    op.create_index(op.f('ix_submissions_problem_id'), 'submissions', ['problem_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_submissions_problem_id'), table_name='submissions')
    op.drop_index(op.f('ix_submissions_id'), table_name='submissions')
    op.drop_index(op.f('ix_submissions_contest_id'), table_name='submissions')
    op.drop_table('submissions')

    op.drop_column('users', 'last_generation_at')
    op.drop_column('users', 'last_submission_at')

    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
