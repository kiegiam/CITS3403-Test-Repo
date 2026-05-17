"""Add profile settings, exercise sets, and plan recommendations.

Revision ID: 0002_exercises_profiles_and_plans
Revises: 0001_initial_schema
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_exercises_profiles_and_plans"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("avatar_filename", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("daily_minutes_goal", sa.Integer(), nullable=False, server_default="20"))
        batch_op.add_column(sa.Column("weight_goal_kg", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("show_public_profile", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("show_public_fitness", sa.Boolean(), nullable=False, server_default=sa.true()))

    op.create_table(
        "plan_recommendations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("main_goal", sa.String(length=100), nullable=False),
        sa.Column("fitness_level", sa.String(length=50), nullable=False),
        sa.Column("training_days", sa.Integer(), nullable=False),
        sa.Column("session_length", sa.Integer(), nullable=False),
        sa.Column("limitation", sa.String(length=200), nullable=True),
        sa.Column("equipment_access", sa.String(length=50), nullable=False, server_default="gym"),
        sa.Column("training_preference", sa.String(length=50), nullable=False, server_default="balanced"),
        sa.Column("recommended_plan", sa.String(length=100), nullable=False),
        sa.Column("recommendation_reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("muscle_group", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "workout_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workout_id", sa.Integer(), sa.ForeignKey("workouts.id"), nullable=False),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id"), nullable=False),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
    )


def downgrade():
    op.drop_table("workout_sets")
    op.drop_table("exercises")
    op.drop_table("plan_recommendations")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("show_public_fitness")
        batch_op.drop_column("show_public_profile")
        batch_op.drop_column("weight_goal_kg")
        batch_op.drop_column("daily_minutes_goal")
        batch_op.drop_column("avatar_filename")
