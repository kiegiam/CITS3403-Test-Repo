"""Create initial FitTrack tables.

Revision ID: 0001_initial_schema
Revises:
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("goal", sa.String(length=200), nullable=True),
        sa.Column("member_since", sa.String(length=50), nullable=True),
        sa.Column("location", sa.String(length=100), nullable=True),
    )

    op.create_table(
        "workouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.String(length=20), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("intensity", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
    )


def downgrade():
    op.drop_table("workouts")
    op.drop_table("users")
