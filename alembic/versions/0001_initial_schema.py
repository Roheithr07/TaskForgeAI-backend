"""Initial TaskForge AI database schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Workflows table
    op.create_table(
        'workflows',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('original_prompt', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=True, default='created'),
        sa.Column('plan_summary', sa.Text(), nullable=True),
        sa.Column('thread_id', sa.String(length=100), nullable=True),
        sa.Column('template_id', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. Workflow Steps table
    op.create_table(
        'workflow_steps',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('workflow_id', sa.String(length=36), nullable=False),
        sa.Column('step_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('tool_input', sa.JSON(), nullable=True),
        sa.Column('tool_output', sa.JSON(), nullable=True),
        sa.Column('dependencies', sa.JSON(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=True, default=0),
        sa.Column('max_retries', sa.Integer(), nullable=True, default=3),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('is_sensitive', sa.Boolean(), nullable=True, default=False),
        sa.Column('status', sa.String(length=50), nullable=True, default='pending'),
        sa.Column('verified', sa.Boolean(), nullable=True, default=False),
        sa.Column('verification_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 3. Approval Requests table
    op.create_table(
        'approval_requests',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('workflow_id', sa.String(length=36), nullable=False),
        sa.Column('step_id', sa.String(length=36), nullable=False),
        sa.Column('requesting_user', sa.String(length=100), nullable=True),
        sa.Column('assigned_reviewer', sa.String(length=100), nullable=True),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('action_description', sa.Text(), nullable=False),
        sa.Column('payload_preview', sa.JSON(), nullable=True),
        sa.Column('payload_hash', sa.String(length=64), nullable=True),
        sa.Column('risk_level', sa.String(length=20), nullable=True, default='HIGH'),
        sa.Column('status', sa.String(length=50), nullable=True, default='pending'),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_by', sa.String(length=100), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('execution_status', sa.String(length=50), nullable=True, default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['step_id'], ['workflow_steps.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 4. Execution Logs table
    op.create_table(
        'execution_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('workflow_id', sa.String(length=36), nullable=False),
        sa.Column('step_id', sa.String(length=36), nullable=True),
        sa.Column('actor', sa.String(length=100), nullable=True),
        sa.Column('level', sa.String(length=20), nullable=True, default='INFO'),
        sa.Column('event', sa.String(length=100), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('outcome', sa.String(length=50), nullable=True, default='SUCCESS'),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('execution_logs')
    op.drop_table('approval_requests')
    op.drop_table('workflow_steps')
    op.drop_table('workflows')

