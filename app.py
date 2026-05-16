import json
import os
import random
import smtplib
from datetime import date, datetime, timedelta
from email.message import EmailMessage

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


app = Flask(__name__)

# ---------------------------------------------------------------------------
# Security: secret key loaded from environment variable.
# Set SECRET_KEY in your .env or shell before running.
# Falls back to a dev default so the app still starts locally without config.
# ---------------------------------------------------------------------------
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me-in-production")

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///fittrack.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# User-uploaded avatar settings
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
app.config["ALLOWED_IMAGE_EXTENSIONS"] = {"png", "jpg", "jpeg", "gif"}

# WTF_CSRF_TIME_LIMIT = None means tokens don't expire with the session
app.config["WTF_CSRF_TIME_LIMIT"] = None

db = SQLAlchemy(app)

# ---------------------------------------------------------------------------
# CSRF protection — applies to every state-changing POST form automatically.
# API routes that use JSON bodies are exempt.
# ---------------------------------------------------------------------------
csrf = CSRFProtect(app)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    goal = db.Column(db.String(200), nullable=True)
    member_since = db.Column(db.String(50), nullable=True)
    location = db.Column(db.String(100), nullable=True)
    avatar_filename = db.Column(db.String(255), nullable=True)
    daily_minutes_goal = db.Column(db.Integer, nullable=False, default=20)
    weight_goal_kg = db.Column(db.Float, nullable=True)

    # Privacy / visibility settings
    show_public_profile = db.Column(db.Boolean, nullable=False, default=True)
    show_public_fitness = db.Column(db.Boolean, nullable=False, default=True)

    workouts = db.relationship(
        "Workout",
        backref="owner",
        lazy=True,
        cascade="all, delete-orphan"
    )

    plan_recommendations = db.relationship(
        "PlanRecommendation",
        backref="owner",
        lazy=True,
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User {self.email}>"


class PlanRecommendation(db.Model):
    __tablename__ = "plan_recommendations"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    main_goal = db.Column(db.String(100), nullable=False)
    fitness_level = db.Column(db.String(50), nullable=False)
    training_days = db.Column(db.Integer, nullable=False)
    session_length = db.Column(db.Integer, nullable=False)
    limitation = db.Column(db.String(200), nullable=True)
    equipment_access = db.Column(db.String(50), nullable=False, default="gym")
    training_preference = db.Column(db.String(50), nullable=False, default="balanced")

    recommended_plan = db.Column(db.String(100), nullable=False)
    recommendation_reason = db.Column(db.Text, nullable=False)
    weekly_structure_json = db.Column(db.Text, nullable=True)
    plan_focus = db.Column(db.String(200), nullable=True)
    suggested_intensity = db.Column(db.String(50), nullable=True)
    plan_badges_json = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<PlanRecommendation user={self.user_id} plan={self.recommended_plan}>"


class Workout(db.Model):
    __tablename__ = "workouts"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    intensity = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text, nullable=True)

    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    sets = db.relationship(
        "WorkoutSet",
        backref="workout",
        lazy=True,
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Workout {self.type} on {self.date}>"


MUSCLE_GROUPS = [
    "Chest",
    "Back",
    "Shoulders",
    "Biceps",
    "Triceps",
    "Legs",
    "Core",
    "Cardio",
]

TRACKING_TYPE_BY_EXERCISE = {
    # Chest
    "Bench Press": "strength",
    "Incline Bench Press": "strength",
    "Dumbbell Fly": "strength",
    "Push-Up": "bodyweight_reps",
    "Cable Crossover": "strength",

    # Back
    "Deadlift": "strength",
    "Pull-Up": "bodyweight_reps",
    "Barbell Row": "strength",
    "Lat Pulldown": "strength",
    "Seated Cable Row": "strength",

    # Shoulders
    "Overhead Press": "strength",
    "Lateral Raise": "strength",
    "Front Raise": "strength",
    "Arnold Press": "strength",
    "Rear Delt Fly": "strength",

    # Biceps
    "Barbell Curl": "strength",
    "Dumbbell Curl": "strength",
    "Hammer Curl": "strength",
    "Preacher Curl": "strength",
    "Cable Curl": "strength",

    # Triceps
    "Tricep Pushdown": "strength",
    "Skull Crusher": "strength",
    "Overhead Tricep Extension": "strength",
    "Close-Grip Bench Press": "strength",
    "Dips": "bodyweight_reps",

    # Legs
    "Squat": "strength",
    "Leg Press": "strength",
    "Romanian Deadlift": "strength",
    "Leg Curl": "strength",
    "Leg Extension": "strength",
    "Calf Raise": "strength",
    "Lunges": "bodyweight_reps",

    # Core
    "Plank": "timed_hold",
    "Crunch": "bodyweight_reps",
    "Hanging Leg Raise": "bodyweight_reps",
    "Russian Twist": "bodyweight_reps",
    "Ab Wheel Rollout": "bodyweight_reps",

    # Cardio
    "Treadmill Run": "cardio_distance",
    "Cycling": "cardio_distance",
    "Rowing Machine": "cardio_distance",
    "Jump Rope": "duration_only",
    "Stair Climber": "stair_climber",
}


def infer_tracking_type(name, muscle_group):
    if name in TRACKING_TYPE_BY_EXERCISE:
        return TRACKING_TYPE_BY_EXERCISE[name]

    exercise_name = (name or "").lower()
    group = (muscle_group or "").lower()

    if "stair" in exercise_name:
        return "stair_climber"

    if any(word in exercise_name for word in [
        "run", "running", "cycle", "cycling", "bike", "biking",
        "row", "rowing", "swim", "swimming", "walk", "walking"
    ]):
        return "cardio_distance"

    if any(word in exercise_name for word in [
        "pull-up", "pull up", "push-up", "push up", "dip", "dips",
        "crunch", "sit-up", "sit up", "leg raise", "rollout", "lunge"
    ]):
        return "bodyweight_reps"

    if any(word in exercise_name for word in [
        "plank", "hold", "wall sit"
    ]):
        return "timed_hold"

    if any(word in exercise_name for word in [
        "jump rope", "stretch", "stretching", "yoga", "mobility"
    ]):
        return "duration_only"

    if group == "cardio":
        return "cardio_distance"

    return "strength"


def infer_tracking_type(name, muscle_group):
    if name in TRACKING_TYPE_BY_EXERCISE:
        return TRACKING_TYPE_BY_EXERCISE[name]

    exercise_name = (name or "").lower()
    group = (muscle_group or "").lower()

    if any(word in exercise_name for word in [
        "run", "running", "cycle", "cycling", "bike", "biking",
        "row", "rowing", "swim", "swimming", "walk", "walking"
    ]):
        return "cardio_distance"

    if any(word in exercise_name for word in [
        "jump rope", "stair", "elliptical"
    ]):
        return "duration_only"

    if any(word in exercise_name for word in [
        "pull-up", "pull up", "push-up", "push up", "dip", "dips",
        "crunch", "sit-up", "sit up", "leg raise", "rollout", "lunge"
    ]):
        return "bodyweight_reps"

    if any(word in exercise_name for word in [
        "plank", "hold", "wall sit"
    ]):
        return "timed_hold"

    if group == "cardio":
        return "duration_only"

    return "strength"


class Exercise(db.Model):
    __tablename__ = "exercises"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    muscle_group = db.Column(db.String(50), nullable=False)

    # NULL = built-in exercise visible to everyone.
    # Set to a user id = custom exercise visible only to that user.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False)
    difficulty_level = db.Column(db.String(50), nullable=True)
    intensity_level = db.Column(db.String(50), nullable=True)
    equipment_type = db.Column(db.String(50), nullable=True)
    plan_tags = db.Column(db.Text, nullable=True)

    sets = db.relationship(
        "WorkoutSet",
        backref="exercise",
        lazy=True
    )

    def __repr__(self):
        return f"<Exercise {self.name} ({self.muscle_group})>"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "muscle_group": self.muscle_group,
            "is_custom": self.user_id is not None,
            "is_archived": self.is_archived,
        }


class WorkoutSet(db.Model):
    __tablename__ = "workout_sets"

    id = db.Column(db.Integer, primary_key=True)
    workout_id = db.Column(db.Integer, db.ForeignKey("workouts.id"), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercises.id"), nullable=False)

    set_number = db.Column(db.Integer, nullable=False)
    reps = db.Column(db.Integer, nullable=False)
    weight_kg = db.Column(db.Float, nullable=False)
    tracking_type = db.Column(db.String(50), nullable=True)
    distance_km = db.Column(db.Float, nullable=True)
    duration_sec = db.Column(db.Integer, nullable=True)
    duration_min = db.Column(db.Integer, nullable=True)
    incline_deg = db.Column(db.Float, nullable=True)

    def __repr__(self):
        return (
            f"<WorkoutSet workout={self.workout_id} "
            f"ex={self.exercise_id} set={self.set_number} "
            f"{self.reps}r @ {self.weight_kg}kg>"
        )

    def to_dict(self):
        return {
            "id": self.id,
            "workout_id": self.workout_id,
            "exercise_id": self.exercise_id,
            "exercise_name": self.exercise.name,
            "muscle_group": self.exercise.muscle_group,
            "set_number": self.set_number,
            "reps": self.reps,
            "weight_kg": self.weight_kg,
        }


def ensure_database_ready():
    with app.app_context():
        db.create_all()

        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

        user_columns = [
            col[1] for col in
            db.session.execute(text("PRAGMA table_info(users)")).fetchall()
        ]

        if "avatar_filename" not in user_columns:
            db.session.execute(
                text("ALTER TABLE users ADD COLUMN avatar_filename VARCHAR(255)")
            )
            db.session.commit()

        if "show_public_profile" not in user_columns:
            db.session.execute(
                text("ALTER TABLE users ADD COLUMN show_public_profile BOOLEAN DEFAULT 1 NOT NULL")
            )
            db.session.commit()

        if "show_public_fitness" not in user_columns:
            db.session.execute(
                text("ALTER TABLE users ADD COLUMN show_public_fitness BOOLEAN DEFAULT 1 NOT NULL")
            )
            db.session.commit()

        if "daily_minutes_goal" not in user_columns:
            db.session.execute(
                text("ALTER TABLE users ADD COLUMN daily_minutes_goal INTEGER DEFAULT 20 NOT NULL")
            )
            db.session.commit()

        if "weight_goal_kg" not in user_columns:
            db.session.execute(
                text("ALTER TABLE users ADD COLUMN weight_goal_kg FLOAT")
            )
            db.session.commit()

        plan_recommendation_columns = [
            col[1] for col in
            db.session.execute(text("PRAGMA table_info(plan_recommendations)")).fetchall()
        ]

        if "equipment_access" not in plan_recommendation_columns:
            db.session.execute(
                text("ALTER TABLE plan_recommendations ADD COLUMN equipment_access VARCHAR(50) DEFAULT 'gym' NOT NULL")
            )
            db.session.commit()

        if "training_preference" not in plan_recommendation_columns:
            db.session.execute(
                text("ALTER TABLE plan_recommendations ADD COLUMN training_preference VARCHAR(50) DEFAULT 'balanced' NOT NULL")
            )
            db.session.commit()

        if "plan_focus" not in plan_recommendation_columns:
            db.session.execute(
                text("ALTER TABLE plan_recommendations ADD COLUMN plan_focus VARCHAR(200)")
            )
            db.session.commit()

        if "suggested_intensity" not in plan_recommendation_columns:
            db.session.execute(
                text("ALTER TABLE plan_recommendations ADD COLUMN suggested_intensity VARCHAR(50)")
            )
            db.session.commit()

        if "plan_badges_json" not in plan_recommendation_columns:
            db.session.execute(
                text("ALTER TABLE plan_recommendations ADD COLUMN plan_badges_json TEXT")
            )
            db.session.commit()

        workout_columns = [
            col[1] for col in
            db.session.execute(text("PRAGMA table_info(workouts)")).fetchall()
        ]

        if "started_at" not in workout_columns:
            db.session.execute(
                text("ALTER TABLE workouts ADD COLUMN started_at DATETIME")
            )
            db.session.commit()

        if "finished_at" not in workout_columns:
            db.session.execute(
                text("ALTER TABLE workouts ADD COLUMN finished_at DATETIME")
            )
            db.session.commit()

        exercise_columns = [
            col[1] for col in
            db.session.execute(text("PRAGMA table_info(exercises)")).fetchall()
        ]

        if "is_archived" not in exercise_columns:
            db.session.execute(
                text("ALTER TABLE exercises ADD COLUMN is_archived BOOLEAN DEFAULT 0 NOT NULL")
            )
            db.session.commit()

        if "difficulty_level" not in exercise_columns:
            db.session.execute(
                text("ALTER TABLE exercises ADD COLUMN difficulty_level VARCHAR(50)")
            )
            db.session.commit()

        if "intensity_level" not in exercise_columns:
            db.session.execute(
                text("ALTER TABLE exercises ADD COLUMN intensity_level VARCHAR(50)")
            )
            db.session.commit()

        if "equipment_type" not in exercise_columns:
            db.session.execute(
                text("ALTER TABLE exercises ADD COLUMN equipment_type VARCHAR(50)")
            )
            db.session.commit()

        if "plan_tags" not in exercise_columns:
            db.session.execute(
                text("ALTER TABLE exercises ADD COLUMN plan_tags TEXT")
            )
            db.session.commit()

        workout_set_columns = [
            col[1] for col in
            db.session.execute(text("PRAGMA table_info(workout_sets)")).fetchall()
        ]

        if "tracking_type" not in workout_set_columns:
            db.session.execute(text("ALTER TABLE workout_sets ADD COLUMN tracking_type VARCHAR(50)"))
            db.session.commit()

        if "distance_km" not in workout_set_columns:
            db.session.execute(text("ALTER TABLE workout_sets ADD COLUMN distance_km FLOAT"))
            db.session.commit()

        if "duration_sec" not in workout_set_columns:
            db.session.execute(text("ALTER TABLE workout_sets ADD COLUMN duration_sec INTEGER"))
            db.session.commit()

        if "duration_min" not in workout_set_columns:
            db.session.execute(text("ALTER TABLE workout_sets ADD COLUMN duration_min INTEGER"))
            db.session.commit()

        if "incline_deg" not in workout_set_columns:
            db.session.execute(text("ALTER TABLE workout_sets ADD COLUMN incline_deg FLOAT"))
            db.session.commit()
        if Exercise.query.filter_by(user_id=None).count() == 0:
            builtin_exercises = [
                Exercise(name="Bench Press", muscle_group="Chest"),
                Exercise(name="Incline Bench Press", muscle_group="Chest"),
                Exercise(name="Dumbbell Fly", muscle_group="Chest"),
                Exercise(name="Push-Up", muscle_group="Chest"),
                Exercise(name="Cable Crossover", muscle_group="Chest"),

                Exercise(name="Deadlift", muscle_group="Back"),
                Exercise(name="Pull-Up", muscle_group="Back"),
                Exercise(name="Barbell Row", muscle_group="Back"),
                Exercise(name="Lat Pulldown", muscle_group="Back"),
                Exercise(name="Seated Cable Row", muscle_group="Back"),

                Exercise(name="Overhead Press", muscle_group="Shoulders"),
                Exercise(name="Lateral Raise", muscle_group="Shoulders"),
                Exercise(name="Front Raise", muscle_group="Shoulders"),
                Exercise(name="Arnold Press", muscle_group="Shoulders"),
                Exercise(name="Rear Delt Fly", muscle_group="Shoulders"),

                Exercise(name="Barbell Curl", muscle_group="Biceps"),
                Exercise(name="Dumbbell Curl", muscle_group="Biceps"),
                Exercise(name="Hammer Curl", muscle_group="Biceps"),
                Exercise(name="Preacher Curl", muscle_group="Biceps"),
                Exercise(name="Cable Curl", muscle_group="Biceps"),

                Exercise(name="Tricep Pushdown", muscle_group="Triceps"),
                Exercise(name="Skull Crusher", muscle_group="Triceps"),
                Exercise(name="Overhead Tricep Extension", muscle_group="Triceps"),
                Exercise(name="Close-Grip Bench Press", muscle_group="Triceps"),
                Exercise(name="Dips", muscle_group="Triceps"),

                Exercise(name="Squat", muscle_group="Legs"),
                Exercise(name="Leg Press", muscle_group="Legs"),
                Exercise(name="Romanian Deadlift", muscle_group="Legs"),
                Exercise(name="Leg Curl", muscle_group="Legs"),
                Exercise(name="Leg Extension", muscle_group="Legs"),
                Exercise(name="Calf Raise", muscle_group="Legs"),
                Exercise(name="Lunges", muscle_group="Legs"),

                Exercise(name="Plank", muscle_group="Core"),
                Exercise(name="Crunch", muscle_group="Core"),
                Exercise(name="Hanging Leg Raise", muscle_group="Core"),
                Exercise(name="Russian Twist", muscle_group="Core"),
                Exercise(name="Ab Wheel Rollout", muscle_group="Core"),

                Exercise(name="Treadmill Run", muscle_group="Cardio"),
                Exercise(name="Cycling", muscle_group="Cardio"),
                Exercise(name="Rowing Machine", muscle_group="Cardio"),
                Exercise(name="Jump Rope", muscle_group="Cardio"),
                Exercise(name="Stair Climber", muscle_group="Cardio"),
            ]

            db.session.add_all(builtin_exercises)
            db.session.commit()

        existing_demo = User.query.filter_by(email="demo@fittrack.com").first()

        if existing_demo is None:
            demo_user = User(
                name="Demo User",
                email="demo@fittrack.com",
                password_hash=generate_password_hash("password123"),
                goal="Stay consistent",
                member_since=date.today().strftime("%B %Y"),
                location="Perth, WA",
                avatar_filename=None,
                show_public_profile=True,
                show_public_fitness=True,
            )

            db.session.add(demo_user)
            db.session.commit()

            sample_workouts = [
                Workout(
                    date="2026-04-20",
                    type="Running",
                    duration=30,
                    intensity="Medium",
                    notes="Felt good and kept a steady pace.",
                    user_id=demo_user.id,
                ),
                Workout(
                    date="2026-04-21",
                    type="Gym",
                    duration=60,
                    intensity="High",
                    notes="Leg day with squats and lunges.",
                    user_id=demo_user.id,
                ),
                Workout(
                    date="2026-04-23",
                    type="Swimming",
                    duration=45,
                    intensity="Medium",
                    notes="Easy pace recovery session.",
                    user_id=demo_user.id,
                ),
                Workout(
                    date="2026-04-24",
                    type="Cycling",
                    duration=40,
                    intensity="Low",
                    notes="Light cardio after class.",
                    user_id=demo_user.id,
                ),
            ]

            db.session.add_all(sample_workouts)
            db.session.commit()


def is_logged_in():
    return "user_id" in session

def allowed_avatar_file(filename):
    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_IMAGE_EXTENSIONS"]
    )

def current_user():
    if "user_id" not in session:
        return None

    return db.session.get(User, session["user_id"])


def build_plan_recommendation(
    main_goal,
    fitness_level,
    training_days,
    session_length,
    limitation,
    equipment_access="gym",
    training_preference="balanced"
):
    goal = (main_goal or "").strip().lower()
    level = (fitness_level or "").strip().lower()
    limit = (limitation or "").strip().lower()
    equipment = (equipment_access or "").strip().lower()
    preference = (training_preference or "").strip().lower()

    try:
        days_per_week = int(training_days)
    except (TypeError, ValueError):
        days_per_week = 4

    days_per_week = max(1, min(days_per_week, 6))

    try:
        minutes_per_session = int(session_length)
    except (TypeError, ValueError):
        minutes_per_session = 30

    minutes_per_session = max(10, minutes_per_session)

    day_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    recommended_plan = "Consistency Starter Plan"
    plan_focus = "Build a repeatable weekly exercise habit."
    suggested_intensity = "Low to Medium"
    plan_badges = ["Balanced", f"{minutes_per_session} min"]
    reason = "This plan keeps training balanced and manageable so it is easier to build a habit."
    focus_pattern = [
        "Strength",
        "Cardio",
        "Recovery",
        "Strength",
        "Flexibility",
        "Cardio",
        "Rest",
    ]

    if "strength" in goal:
        recommended_plan = "Strength Builder Plan"
        plan_focus = "Build strength with repeated full-body training."
        suggested_intensity = "Medium to High"
        plan_badges = ["Strength", f"{minutes_per_session} min"]
        reason = "This plan prioritises strength sessions with recovery between harder training days."
        focus_pattern = [
            "Strength",
            "Recovery",
            "Strength",
            "Cardio",
            "Strength",
            "Flexibility",
            "Rest",
        ]

        if level == "beginner":
            recommended_plan = "Beginner Strength Starter"
            suggested_intensity = "Low to Medium"
            plan_badges.append("Beginner friendly")

        if level == "intermediate" and days_per_week >= 4:
            recommended_plan = "Full Body Strength Plan"
            plan_badges.append("Full body")

        if equipment in ["home", "bodyweight_only"]:
            recommended_plan = "Bodyweight Home Plan"
            plan_focus = "Build strength using home-friendly or bodyweight sessions."
            suggested_intensity = "Low to Medium"
            plan_badges.extend(["Home friendly", "No gym needed"])
            focus_pattern = [
                "Bodyweight strength",
                "Recovery",
                "Bodyweight strength",
                "Cardio",
                "Core strength",
                "Flexibility",
                "Rest",
            ]

    elif "cardio" in goal:
        recommended_plan = "Cardio Endurance Plan"
        plan_focus = "Improve endurance with regular cardio and supporting strength."
        suggested_intensity = "Medium"
        plan_badges = ["Cardio", f"{minutes_per_session} min"]
        reason = "This plan increases cardio frequency while keeping some strength and mobility work."
        focus_pattern = [
            "Cardio",
            "Strength",
            "Cardio",
            "Recovery",
            "Cardio",
            "Flexibility",
            "Rest",
        ]

        if "knee" in limit or preference == "low_impact":
            recommended_plan = "Low Impact Cardio Plan"
            plan_focus = "Build cardio fitness with joint-friendly exercise choices."
            suggested_intensity = "Low to Medium"
            plan_badges.extend(["Low impact", "Joint friendly"])

    elif "weight" in goal or "lose" in goal:
        recommended_plan = "Balanced Fat Loss Plan"
        plan_focus = "Combine cardio, strength, and recovery for consistent activity."
        suggested_intensity = "Medium"
        plan_badges = ["Balanced", "Cardio + strength", f"{minutes_per_session} min"]
        reason = "This plan mixes cardio, strength, and recovery to support consistent weekly activity."
        focus_pattern = [
            "Cardio",
            "Strength",
            "Recovery",
            "Cardio",
            "Strength",
            "Flexibility",
            "Rest",
        ]

        if preference == "challenge" and level == "advanced":
            recommended_plan = "Conditioning Challenge Plan"
            plan_focus = "Use a more demanding mix of conditioning and strength."
            suggested_intensity = "Medium to High"
            plan_badges.extend(["Challenge", "Advanced"])

    elif "flexibility" in goal:
        recommended_plan = "Flexibility Foundation Plan"
        plan_focus = "Improve mobility and recovery with regular flexibility work."
        suggested_intensity = "Low"
        plan_badges = ["Flexibility", "Recovery", f"{minutes_per_session} min"]
        reason = "This plan emphasises flexibility, mobility, and recovery with light supporting activity."
        focus_pattern = [
            "Flexibility",
            "Recovery",
            "Flexibility",
            "Core stability",
            "Flexibility",
            "Low-impact cardio",
            "Rest",
        ]

        if "back" in limit or preference == "low_impact":
            recommended_plan = "Mobility and Recovery Plan"
            plan_focus = "Prioritise gentle mobility, recovery, and core stability."
            plan_badges.extend(["Low impact", "Core stability"])

    if "consistency" in goal:
        recommended_plan = "Consistency Starter Plan"
        plan_focus = "Build a low-pressure routine that is easy to repeat."
        suggested_intensity = "Low to Medium"
        plan_badges = ["Beginner friendly", "Habit building", f"{minutes_per_session} min"]
        reason = "This plan keeps training balanced and manageable so it is easier to build a habit."

        if level == "beginner":
            plan_badges.append("Beginner friendly")

    if minutes_per_session <= 20 or preference == "short_simple":
        recommended_plan = "Short Session Habit Plan"
        plan_focus = "Keep sessions short, simple, and easy to complete."
        suggested_intensity = "Low to Medium"
        plan_badges = ["Short sessions", f"{minutes_per_session} min", "Simple"]
        reason = "This plan uses shorter sessions to make training feel realistic and repeatable."
        focus_pattern = [
            "Strength",
            "Cardio",
            "Recovery",
            "Strength",
            "Flexibility",
            "Cardio",
            "Rest",
        ]

    if level == "advanced" and preference == "challenge":
        recommended_plan = "Conditioning Challenge Plan"
        plan_focus = "Push conditioning with a more challenging weekly structure."
        suggested_intensity = "Medium to High"
        plan_badges = ["Challenge", "Advanced", f"{minutes_per_session} min"]
        reason = "This plan suits an advanced user who wants a more challenging conditioning focus."
        focus_pattern = [
            "Conditioning",
            "Strength",
            "Cardio intervals",
            "Recovery",
            "Conditioning",
            "Flexibility",
            "Rest",
        ]

    active_days = 0
    weekly_structure = []

    for index, day_name in enumerate(day_names):
        focus = focus_pattern[index]

        if focus != "Rest" and active_days >= days_per_week:
            focus = "Recovery" if index < 6 else "Rest"

        if focus not in ["Rest", "Recovery"]:
            active_days += 1

        note = f"Aim for about {minutes_per_session} minutes."

        if focus == "Recovery":
            note = "Keep this light with stretching, walking, or mobility work."
        elif focus == "Rest":
            note = "Take a full rest day or do gentle movement only."

        weekly_structure.append({
            "day_name": day_name,
            "focus": focus,
            "note": note,
        })

    if "beginner" in level:
        reason += " Because you selected beginner level, the structure keeps intensity approachable."
    elif "advanced" in level:
        reason += " Because you selected advanced level, the structure allows more focused training days."

    if equipment == "gym":
        reason += " Gym access gives you more equipment options."
        plan_badges.append("Gym access")
    elif equipment == "home":
        reason += " Home access means the plan keeps exercises practical outside a gym."
        plan_badges.append("Home friendly")
    elif equipment == "outdoor":
        reason += " Outdoor access works well for walking, running, cycling, and simple conditioning."
        plan_badges.append("Outdoor")
    elif equipment == "bodyweight_only":
        reason += " Bodyweight-only access keeps the plan simple and equipment-free."
        plan_badges.append("Bodyweight")

    if "knee" in limit:
        reason += " With knee discomfort, it favours lower-impact cardio and avoids heavy leg emphasis."
        suggested_intensity = "Low to Medium"
        plan_badges.append("Low impact")

        for day in weekly_structure:
            if day["focus"] in ["Cardio", "Cardio intervals", "Conditioning"]:
                day["focus"] = "Low-impact cardio"
                day["note"] = "Choose cycling, rowing, swimming, or another low-impact option."
            elif "strength" in day["focus"].lower():
                day["note"] = "Keep leg loading moderate and avoid heavy knee-dominant work."

    if "back" in limit:
        reason += " With back discomfort, it avoids heavy lifting focus and adds core stability language."
        plan_badges.append("Core stability")

        for day in weekly_structure:
            if "strength" in day["focus"].lower():
                day["focus"] = "Controlled strength"
                day["note"] = "Use controlled movements and avoid heavy loading."
            elif day["focus"] == "Recovery":
                day["note"] = "Focus on gentle mobility and core stability."

    if "shoulder" in limit:
        reason += " With shoulder discomfort, it limits repeated upper-body strength focus."
        plan_badges.append("Shoulder mindful")

        strength_seen = 0
        for day in weekly_structure:
            if "strength" in day["focus"].lower():
                strength_seen += 1

                if strength_seen > 1:
                    day["focus"] = "Lower-body or core strength"
                    day["note"] = "Avoid too much upper-body pressing or shoulder-heavy work."

    if "low energy" in limit or "energy" in limit:
        reason += " With low energy, it recommends shorter sessions and extra recovery."
        suggested_intensity = "Low"
        plan_badges.append("Extra recovery")
        minutes_per_session = min(minutes_per_session, 25)
        changed_day = False

        for day in weekly_structure:
            if day["focus"] not in ["Rest", "Recovery"] and not changed_day:
                day["focus"] = "Recovery"
                day["note"] = "Use this as an easier day to keep momentum without overdoing it."
                changed_day = True
            elif day["focus"] not in ["Rest", "Recovery"]:
                day["note"] = f"Keep this short and manageable, around {minutes_per_session} minutes."

    if preference == "structured":
        reason += " Your structured preference is reflected in a clear day-by-day schedule."
        plan_badges.append("Structured")
    elif preference == "low_impact":
        reason += " Your low-impact preference keeps the plan gentler on joints."
        suggested_intensity = "Low to Medium"
        plan_badges.append("Low impact")
    elif preference == "balanced":
        reason += " Your balanced preference keeps the plan varied across training types."
        plan_badges.append("Balanced")

    plan_badges = list(dict.fromkeys(plan_badges))
    reason += " This is general fitness planning guidance, not medical advice."

    return {
        "recommended_plan": recommended_plan,
        "recommendation_reason": reason,
        "weekly_structure": weekly_structure,
        "plan_focus": plan_focus,
        "suggested_intensity": suggested_intensity,
        "plan_badges": plan_badges,
    }


def allowed_image(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_IMAGE_EXTENSIONS"]
    )


def is_valid_password(password, minimum_length=6):
    if any(char.isspace() for char in password):
        return False

    return len(password) >= minimum_length


def send_reset_code_email(to_email, code):
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user or not smtp_password or not smtp_from:
        print("==================================================")
        print("Password reset code for local development")
        print(f"Email: {to_email}")
        print(f"Code: {code}")
        print("SMTP is not configured, so no real email was sent.")
        print("==================================================")
        return True

    message = EmailMessage()
    message["Subject"] = "Your FitTrack password reset code"
    message["From"] = smtp_from
    message["To"] = to_email
    message.set_content(
        f"Your FitTrack password reset code is: {code}\n\n"
        "This code will expire in 10 minutes.\n\n"
        "If you did not request this, you can ignore this email."
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(message)
        return True
    except Exception as error:
        print(f"Failed to send reset email: {error}")
        return False


def user_to_profile_dict(user):
    return {
        "name": user.name,
        "email": user.email,
        "goal": user.goal or "No goal set yet.",
        "member_since": user.member_since or "Unknown",
        "location": user.location or "Not set",
        "avatar_filename": user.avatar_filename,
        "show_public_profile": bool(user.show_public_profile),
        "show_public_fitness": bool(user.show_public_fitness),
    }


@app.context_processor
def inject_nav_profile():
    user = current_user()

    if user is None:
        return {
            "nav_profile": None,
            "nav_email": None,
        }

    return {
        "nav_profile": user_to_profile_dict(user),
        "nav_email": user.email,
    }


def workout_to_dict(workout):
    return {
        "id": workout.id,
        "date": workout.date,
        "type": workout.type,
        "duration": workout.duration,
        "intensity": workout.intensity,
        "notes": workout.notes or "No notes added.",
    }


def get_user_workout(user, workout_id):
    return Workout.query.filter_by(
        id=workout_id,
        user_id=user.id
    ).first()


def calculate_streak(user_workouts):
    today = date.today()
    workout_dates = set()

    for workout in user_workouts:
        try:
            workout_date = date.fromisoformat(workout.date)

            if workout_date <= today:
                workout_dates.add(workout_date)
        except ValueError:
            continue

    if not workout_dates:
        return 0

    streak = 0
    check_date = today

    while check_date in workout_dates:
        streak += 1
        check_date -= timedelta(days=1)

    if streak == 0:
        check_date = today - timedelta(days=1)

        while check_date in workout_dates:
            streak += 1
            check_date -= timedelta(days=1)

    return streak


def get_statistics(user):
    user_workouts = Workout.query.filter_by(user_id=user.id).all()

    total_workouts = len(user_workouts)
    total_minutes = sum(workout.duration for workout in user_workouts)
    current_streak = calculate_streak(user_workouts)

    return {
        "total_workouts": total_workouts,
        "total_minutes": total_minutes,
        "current_streak": current_streak,
    }


def get_progress_data(user):
    user_workouts = Workout.query.filter_by(user_id=user.id).all()

    total_workouts = len(user_workouts)
    total_minutes = sum(workout.duration for workout in user_workouts)

    if total_workouts == 0:
        average_duration = 0
    else:
        average_duration = round(total_minutes / total_workouts)

    type_counts = {}
    type_minutes = {}

    for workout in user_workouts:
        workout_type = workout.type

        if workout_type not in type_counts:
            type_counts[workout_type] = 0
            type_minutes[workout_type] = 0

        type_counts[workout_type] += 1
        type_minutes[workout_type] += workout.duration

    if type_counts:
        most_common_type = max(type_counts, key=type_counts.get)
    else:
        most_common_type = "None"

    progress_stats = {
        "total_workouts": total_workouts,
        "total_minutes": total_minutes,
        "average_duration": average_duration,
        "current_streak": calculate_streak(user_workouts),
        "most_common_type": most_common_type,
    }

    return progress_stats, type_counts, type_minutes

def parse_workout_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    
def allowed_avatar_file(filename):
    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_IMAGE_EXTENSIONS"]
    )

@app.route("/api/workout-chart-data")
def api_workout_chart_data():
    if not is_logged_in():
        return jsonify({"error": "Unauthorised"}), 401

    user = current_user()

    if user is None:
        return jsonify({"error": "Unauthorised"}), 401

    range_days = request.args.get("range", "30")
    intensity_filter = request.args.get("intensity", "All")
    metric = request.args.get("metric", "duration")

    try:
        range_days = int(range_days)
    except ValueError:
        range_days = 30

    if range_days not in [7, 30, 90]:
        range_days = 30

    if intensity_filter not in ["All", "Low", "Medium", "High"]:
        intensity_filter = "All"

    if metric not in ["duration", "count"]:
        metric = "duration"

    today = date.today()
    start_date = today - timedelta(days=range_days - 1)

    user_workouts = Workout.query.filter_by(user_id=user.id).all()
    filtered_workouts = []

    for workout in user_workouts:
        try:
            workout_date = date.fromisoformat(workout.date)
        except ValueError:
            continue

        if workout_date < start_date or workout_date > today:
            continue

        if intensity_filter != "All" and workout.intensity != intensity_filter:
            continue

        filtered_workouts.append(workout)

    labels = []
    duration_values = []
    count_values = []

    for day_offset in range(range_days):
        current_date = start_date + timedelta(days=day_offset)
        current_date_text = current_date.isoformat()

        day_workouts = [
            workout for workout in filtered_workouts
            if workout.date == current_date_text
        ]

        total_duration = sum(workout.duration for workout in day_workouts)
        workout_count = len(day_workouts)

        labels.append(current_date_text)
        duration_values.append(total_duration)
        count_values.append(workout_count)

    intensity_counts = {
        "Low": 0,
        "Medium": 0,
        "High": 0,
    }

    for workout in filtered_workouts:
        if workout.intensity in intensity_counts:
            intensity_counts[workout.intensity] += 1

    total_workouts = len(filtered_workouts)
    total_minutes = sum(workout.duration for workout in filtered_workouts)

    if total_workouts == 0:
        average_minutes = 0
    else:
        average_minutes = round(total_minutes / total_workouts, 1)

    workout_details = []

    for workout in filtered_workouts:
        workout_details.append({
            "id": workout.id,
            "date": workout.date,
            "type": workout.type,
            "duration": workout.duration,
            "intensity": workout.intensity,
            "notes": workout.notes or "No notes added.",
            "edit_url": url_for("edit_workout", workout_id=workout.id),
            "delete_url": url_for("delete_workout", workout_id=workout.id),
        })

    return jsonify({
        "range": range_days,
        "intensity": intensity_filter,
        "metric": metric,
        "labels": labels,
        "durations": duration_values,
        "counts": count_values,
        "intensity_counts": intensity_counts,
        "summary": {
            "total_workouts": total_workouts,
            "total_minutes": total_minutes,
            "average_minutes": average_minutes,
        },
        "workouts": workout_details,
    })


@app.route("/")
def home():
    if is_logged_in():
        session.clear()
        flash("You were logged in on a previous session. You have been logged out.", "success")
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password or not confirm_password:
            flash("Name, email, password, and confirm password are required.")
            return render_template("register.html")

        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("This email is already registered. Please log in or use another email.")
            return render_template("register.html")

        if not is_valid_password(password, 6):
            flash("Password must be at least 6 characters and cannot contain spaces.")
            return render_template("register.html")

        if password != confirm_password:
            flash("Password and confirm password do not match.")
            return render_template("register.html")

        new_user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            goal="Stay consistent",
            member_since=date.today().strftime("%B %Y"),
            location="Not set",
            avatar_filename=None,
            show_public_profile=True,
            show_public_fitness=True,
        )

        db.session.add(new_user)
        db.session.commit()

        session["user_id"] = new_user.id
        session["user_email"] = new_user.email

        flash("Account created successfully.")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["user_email"] = user.email
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Please enter your email address.")
            return render_template("forgot_password.html")

        user = User.query.filter_by(email=email).first()

        if user is None:
            flash("No account was found with that email address.")
            return render_template("forgot_password.html")

        reset_code = str(random.randint(100000, 999999))
        expires_at = datetime.now() + timedelta(minutes=10)

        session["reset_email"] = email
        session["reset_code"] = reset_code
        session["reset_code_expires_at"] = expires_at.isoformat()
        session["reset_verified"] = False

        email_sent = send_reset_code_email(email, reset_code)

        if not email_sent:
            flash("The reset code could not be sent. Please try again later.")
            return render_template("forgot_password.html")

        flash("A verification code has been sent to your email.")
        return redirect(url_for("verify_reset_code"))

    return render_template("forgot_password.html")


@app.route("/verify-reset-code", methods=["GET", "POST"])
def verify_reset_code():
    if "reset_email" not in session or "reset_code" not in session:
        flash("Please request a password reset code first.")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        entered_code = request.form.get("code", "").strip()
        stored_code = session.get("reset_code")
        expires_at_text = session.get("reset_code_expires_at")

        try:
            expires_at = datetime.fromisoformat(expires_at_text)
        except (TypeError, ValueError):
            flash("The verification session is invalid. Please request a new code.")
            return redirect(url_for("forgot_password"))

        if datetime.now() > expires_at:
            session.pop("reset_code", None)
            session.pop("reset_code_expires_at", None)
            session["reset_verified"] = False
            flash("The verification code has expired. Please request a new code.")
            return redirect(url_for("forgot_password"))

        if entered_code != stored_code:
            flash("The verification code is incorrect.")
            return render_template("verify_reset_code.html", email=session.get("reset_email"))

        session["reset_verified"] = True
        flash("Verification successful. Please set a new password.")
        return redirect(url_for("reset_password"))

    return render_template("verify_reset_code.html", email=session.get("reset_email"))


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if not session.get("reset_verified") or "reset_email" not in session:
        flash("Please verify your reset code first.")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not password or not confirm_password:
            flash("Password and confirm password are required.")
            return render_template("reset_password.html")

        if not is_valid_password(password, 6):
            flash("Password must be at least 6 characters and cannot contain spaces.")
            return render_template("reset_password.html")

        if password != confirm_password:
            flash("Password and confirm password do not match.")
            return render_template("reset_password.html")

        user = User.query.filter_by(email=session["reset_email"]).first()

        if user is None:
            flash("Account not found. Please request a new password reset.")
            return redirect(url_for("forgot_password"))

        user.password_hash = generate_password_hash(password)
        db.session.commit()

        session.pop("reset_email", None)
        session.pop("reset_code", None)
        session.pop("reset_code_expires_at", None)
        session.pop("reset_verified", None)

        flash("Password reset successfully. Please log in.")
        return redirect(url_for("login"))

    return render_template("reset_password.html")


@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    recent_workout_objects = (
        Workout.query
        .filter_by(user_id=user.id)
        .order_by(Workout.date.desc(), Workout.id.desc())
        .limit(3)
        .all()
    )

    recent_workouts = [
        workout_to_dict(workout)
        for workout in recent_workout_objects
    ]

    statistics = get_statistics(user)

    return render_template(
        "dashboard.html",
        email=user.email,
        recent_workouts=recent_workouts,
        statistics=statistics,
    )


@app.route("/profile")
def profile():
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    statistics = get_statistics(user)
    profile_data = user_to_profile_dict(user)

    return render_template(
        "profile.html",
        profile=profile_data,
        statistics=statistics,
    )


@app.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    if request.method == "POST":
        action = request.form.get("action", "save")

        if action == "remove_avatar":
            if user.avatar_filename:
                old_avatar_path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    user.avatar_filename
                )

                if os.path.exists(old_avatar_path):
                    os.remove(old_avatar_path)

                user.avatar_filename = None
                db.session.commit()

            flash("Profile picture removed. Default initials will now be used.", "success")
            return redirect(url_for("edit_profile"))

        name = request.form.get("name", "").strip()
        goal = request.form.get("goal", "").strip()
        location = request.form.get("location", "").strip()
        avatar_file = request.files.get("avatar")

        if not name:
            flash("Name cannot be empty.", "danger")
            return render_template(
                "edit_profile.html",
                profile=user_to_profile_dict(user)
            )

        user.name = name
        user.goal = goal or "Stay consistent"
        user.location = location or "Not set"

        if avatar_file and avatar_file.filename:
            if not allowed_avatar_file(avatar_file.filename):
                flash("Please upload a valid image file: PNG, JPG, JPEG, or GIF.", "danger")
                return render_template(
                    "edit_profile.html",
                    profile=user_to_profile_dict(user)
                )

            if user.avatar_filename:
                old_avatar_path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    user.avatar_filename
                )
                if os.path.exists(old_avatar_path):
                    os.remove(old_avatar_path)

            original_name = secure_filename(avatar_file.filename)
            extension = original_name.rsplit(".", 1)[1].lower()
            new_filename = f"{user.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{extension}"

            save_path = os.path.join(app.config["UPLOAD_FOLDER"], new_filename)
            avatar_file.save(save_path)

            user.avatar_filename = new_filename

        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    return render_template("edit_profile.html", profile=user_to_profile_dict(user))


@app.route("/workouts")
def workouts():
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    search_query = request.args.get("search", "").strip()
    intensity_filter = request.args.get("intensity", "").strip()
    sort_by = request.args.get("sort", "newest").strip()

    query = Workout.query.filter_by(user_id=user.id)

    if search_query:
        query = query.filter(Workout.type.ilike(f"%{search_query}%"))

    if intensity_filter:
        query = query.filter(Workout.intensity == intensity_filter)

    if sort_by == "oldest":
        query = query.order_by(Workout.date.asc(), Workout.id.asc())
    elif sort_by == "longest":
        query = query.order_by(Workout.duration.desc())
    elif sort_by == "shortest":
        query = query.order_by(Workout.duration.asc())
    else:
        query = query.order_by(Workout.date.desc(), Workout.id.desc())

    workout_list = [workout_to_dict(workout) for workout in query.all()]

    return render_template(
        "workouts.html",
        workouts=workout_list,
        search_query=search_query,
        intensity_filter=intensity_filter,
        sort_by=sort_by,
    )


@app.route("/workouts/add")
def add_workout():
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    selected_plan = request.args.get("plan", "").strip().lower()

    if selected_plan not in ["strength", "cardio", "flexibility"]:
        selected_plan = ""

    return render_template(
        "add_workout.html",
        muscle_groups=MUSCLE_GROUPS,
        selected_plan=selected_plan,
    )


@csrf.exempt
@app.route("/api/exercises")
def api_exercises():
    if not is_logged_in():
        return jsonify({"error": "Unauthorised"}), 401

    user = current_user()

    if user is None:
        return jsonify({"error": "Unauthorised"}), 401

    muscle_group = request.args.get("muscle_group", "").strip()

    if not muscle_group:
        return jsonify({"error": "muscle_group parameter is required"}), 400

    exercises = Exercise.query.filter(
        Exercise.muscle_group == muscle_group,
        Exercise.is_archived == False,
        db.or_(
            Exercise.user_id == None,   # built-ins
            Exercise.user_id == user.id # user's own custom exercises
        )
    ).order_by(Exercise.name).all()

    return jsonify([exercise.to_dict() for exercise in exercises])


@csrf.exempt
@app.route("/api/exercises", methods=["POST"])
def api_add_exercise():
    if not is_logged_in():
        return jsonify({"error": "Unauthorised"}), 401

    user = current_user()

    if user is None:
        return jsonify({"error": "Unauthorised"}), 401

    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "JSON body required"}), 400
    duration_mode = (data.get("duration_mode") or "stopwatch").strip().lower()
    manual_duration_min = data.get("manual_duration_min")

    name = (data.get("name") or "").strip()
    muscle_group = (data.get("muscle_group") or "").strip()

    if not name:
        return jsonify({"error": "Exercise name is required"}), 400

    if muscle_group not in MUSCLE_GROUPS:
        return jsonify({"error": f"muscle_group must be one of: {', '.join(MUSCLE_GROUPS)}"}), 400

        # Prevent duplicates among built-ins and active custom exercises.
    duplicate = Exercise.query.filter(
        Exercise.name.ilike(name),
        Exercise.muscle_group == muscle_group,
        db.or_(Exercise.user_id == None, Exercise.user_id == user.id),
        Exercise.is_archived == False,
    ).first()

    if duplicate:
        return jsonify({"error": "An exercise with that name already exists in this muscle group"}), 409

    # If this user previously archived the same custom exercise,
    # restore it instead of creating a duplicate row.
    archived_duplicate = Exercise.query.filter(
        Exercise.name.ilike(name),
        Exercise.muscle_group == muscle_group,
        Exercise.user_id == user.id,
        Exercise.is_archived == True,
    ).first()

    if archived_duplicate:
        archived_duplicate.is_archived = False
        db.session.commit()
        return jsonify(archived_duplicate.to_dict()), 200

    new_exercise = Exercise(
        name=name,
        muscle_group=muscle_group,
        user_id=user.id,
    )

    db.session.add(new_exercise)
    db.session.commit()

    return jsonify(new_exercise.to_dict()), 201

@app.route("/api/exercises/<int:exercise_id>", methods=["DELETE"])
@csrf.exempt
def api_delete_exercise(exercise_id):
    if not is_logged_in():
        return jsonify({"error": "Unauthorised"}), 401

    user = current_user()
    if user is None:
        return jsonify({"error": "Unauthorised"}), 401

    # Only the logged-in user's own custom exercises can be archived.
    # Built-in exercises have user_id=None and cannot be archived by users.
    exercise = Exercise.query.filter_by(
        id=exercise_id,
        user_id=user.id
    ).first()

    if exercise is None:
        return jsonify({"error": "Custom exercise not found"}), 404

    exercise.is_archived = True
    db.session.commit()

    return jsonify({"success": True}), 200

@csrf.exempt
@app.route("/workouts/finish", methods=["POST"])
def finish_workout():
    if not is_logged_in():
        return jsonify({"error": "Unauthorised"}), 401

    user = current_user()

    if user is None:
        return jsonify({"error": "Unauthorised"}), 401

    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "JSON body required"}), 400

    duration_mode = (data.get("duration_mode") or "stopwatch").strip().lower()
    manual_duration_minutes = data.get("manual_duration_minutes")

    try:
        started_at = datetime.fromisoformat(data["started_at"])
        finished_at = datetime.fromisoformat(data["finished_at"])
    except (KeyError, ValueError):
        return jsonify({"error": "started_at and finished_at must be valid ISO datetime strings"}), 400

    if duration_mode == "manual":
        try:
            duration_minutes = int(manual_duration_minutes or 0)
        except (TypeError, ValueError):
            return jsonify({"error": "Manual duration must be a whole number of minutes"}), 400

        if duration_minutes <= 0:
            return jsonify({"error": "Manual duration must be greater than 0"}), 400

        if finished_at <= started_at:
            finished_at = started_at + timedelta(minutes=duration_minutes)
    else:
        if finished_at <= started_at:
            return jsonify({"error": "finished_at must be after started_at"}), 400

        duration_seconds = int((finished_at - started_at).total_seconds())
        duration_minutes = max(1, round(duration_seconds / 60))

    raw_sets = data.get("sets", [])

    if not raw_sets:
        return jsonify({"error": "At least one set is required"}), 400

    validated_sets = []

    for index, raw_set in enumerate(raw_sets):
        try:
            exercise_id = int(raw_set["exercise_id"])
            set_number = int(raw_set["set_number"])
            tracking_type = (raw_set.get("tracking_type") or "strength").strip().lower()

            reps = int(raw_set.get("reps", 0) or 0)
            weight_kg = float(raw_set.get("weight_kg", 0) or 0)
            distance_km = float(raw_set.get("distance_km", 0) or 0)
            duration_sec = int(raw_set.get("duration_sec", 0) or 0)
            duration_min = int(raw_set.get("duration_min", 0) or 0)
        except (KeyError, ValueError, TypeError):
            return jsonify({"error": f"Set {index} is missing or has invalid fields"}), 400

        exercise = Exercise.query.filter(
            Exercise.id == exercise_id,
            db.or_(Exercise.user_id == None, Exercise.user_id == user.id)
        ).first()

        if exercise is None:
            return jsonify({"error": f"Set {index}: exercise_id {exercise_id} not found"}), 404

        if tracking_type == "strength":
            if reps <= 0:
                return jsonify({"error": f"Set {index}: reps must be greater than 0"}), 400
            if weight_kg < 0:
                return jsonify({"error": f"Set {index}: weight_kg cannot be negative"}), 400

        elif tracking_type == "bodyweight_reps":
            if reps <= 0:
                return jsonify({"error": f"Set {index}: reps must be greater than 0"}), 400

        elif tracking_type == "cardio_distance":
            if distance_km <= 0:
                return jsonify({"error": f"Set {index}: distance_km must be greater than 0"}), 400

        elif tracking_type == "timed_hold":
            if duration_sec <= 0:
                return jsonify({"error": f"Set {index}: duration_sec must be greater than 0"}), 400

        elif tracking_type == "duration_only":
            if duration_min <= 0:
                return jsonify({"error": f"Set {index}: duration_min must be greater than 0"}), 400
            
        elif tracking_type == "stair_climber":
            if distance_km <= 0:
                return jsonify({"error": f"Set {index}: distance_km must be greater than 0"}), 400

            if incline_deg < 0 or incline_deg > 90:
                return jsonify({"error": f"Set {index}: incline_deg must be between 0 and 90"}), 400

        validated_sets.append({
            "exercise": exercise,
            "set_number": set_number,
            "tracking_type": tracking_type,
            "reps": reps,
            "weight_kg": weight_kg,
            "distance_km": distance_km,
            "duration_sec": duration_sec,
            "duration_min": duration_min,
        })

    muscle_groups_trained = list(dict.fromkeys(
        saved_set["exercise"].muscle_group
        for saved_set in validated_sets
    ))

    workout_type = ", ".join(muscle_groups_trained)

    intensity = (data.get("intensity") or "Medium").strip().title()

    if intensity not in {"Low", "Medium", "High"}:
        return jsonify({"error": "Intensity must be Low, Medium, or High"}), 400

    notes = (data.get("notes") or "").strip() or "No notes added."

    new_workout = Workout(
        date=started_at.strftime("%Y-%m-%d"),
        type=workout_type,
        duration=duration_minutes,
        intensity=intensity,
        notes=notes,
        started_at=started_at,
        finished_at=finished_at,
        user_id=user.id,
    )

    db.session.add(new_workout)
    db.session.commit()

    total_volume_kg = sum(saved_set["reps"] * saved_set["weight_kg"] for saved_set in validated_sets)

    exercise_summary = {}
    for saved_set in validated_sets:
        name = saved_set["exercise"].name
        exercise_summary[name] = exercise_summary.get(name, 0) + 1

    return jsonify({
        "success": True,
        "duration_minutes": duration_minutes,
        "total_sets": len(validated_sets),
        "total_volume_kg": total_volume_kg,
        "intensity": intensity,
        "muscle_groups": muscle_groups_trained,
        "exercises": exercise_summary,
    }), 200


@app.route("/workouts/<int:workout_id>/edit", methods=["GET", "POST"])
def edit_workout(workout_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    workout = Workout.query.filter_by(id=workout_id, user_id=user.id).first_or_404()

    if request.method == "POST":
        workout_date = request.form.get("date", "").strip()
        workout_type = request.form.get("type", "").strip()
        duration = request.form.get("duration", "").strip()
        intensity = request.form.get("intensity", "").strip()
        notes = request.form.get("notes", "").strip()

        if not workout_date or not workout_type or not duration or not intensity:
            flash("Please complete all required fields.", "danger")
            return render_template(
                "edit_workout.html",
                workout=workout_to_dict(workout),
                today_date=date.today().isoformat()
            )

        try:
            selected_date = datetime.strptime(workout_date, "%Y-%m-%d").date()
        except ValueError:
            flash("Please enter a valid date.", "danger")
            return render_template(
                "edit_workout.html",
                workout=workout_to_dict(workout),
                today_date=date.today().isoformat()
            )

        if selected_date > date.today():
            flash("Please enter a valid date. Workout date cannot be later than today.", "danger")
            return render_template(
                "edit_workout.html",
                workout=workout_to_dict(workout),
                today_date=date.today().isoformat()
            )

        try:
            duration_value = int(duration)
        except ValueError:
            flash("Duration must be a number.", "danger")
            return render_template(
                "edit_workout.html",
                workout=workout_to_dict(workout),
                today_date=date.today().isoformat()
            )

        if duration_value <= 0:
            flash("Duration must be greater than 0.", "danger")
            return render_template(
                "edit_workout.html",
                workout=workout_to_dict(workout),
                today_date=date.today().isoformat()
            )

        workout.date = workout_date
        workout.type = workout_type
        workout.duration = duration_value
        workout.intensity = intensity
        workout.notes = notes or "No notes added."

        db.session.commit()
        flash("Workout updated successfully.", "success")
        return redirect(url_for("workouts"))

    return render_template(
        "edit_workout.html",
        workout=workout_to_dict(workout),
        today_date=date.today().isoformat()
    )

@app.route("/workouts/<int:workout_id>/delete", methods=["POST"])
def delete_workout(workout_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    workout = get_user_workout(user, workout_id)

    if workout is None:
        flash("Workout not found.")
        return redirect(url_for("workouts"))

    db.session.delete(workout)
    db.session.commit()

    flash("Workout deleted successfully.")
    return redirect(url_for("workouts"))


@app.route("/progress")
def progress():
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    progress_stats, type_counts, type_minutes = get_progress_data(user)

    recent_workout_objects = (
        Workout.query
        .filter_by(user_id=user.id)
        .order_by(Workout.date.desc(), Workout.id.desc())
        .all()
    )

    recent_workouts = [
        workout_to_dict(workout)
        for workout in recent_workout_objects
    ]

    type_chart_labels = list(type_counts.keys())
    type_chart_counts = list(type_counts.values())
    minutes_chart_labels = list(type_minutes.keys())
    minutes_chart_values = list(type_minutes.values())

    trend_minutes_by_date = {}

    for workout in recent_workout_objects:
        if workout.date not in trend_minutes_by_date:
            trend_minutes_by_date[workout.date] = 0

        trend_minutes_by_date[workout.date] += workout.duration

    trend_chart_labels = sorted(trend_minutes_by_date.keys())
    trend_chart_minutes = [
        trend_minutes_by_date[workout_date]
        for workout_date in trend_chart_labels
    ]

    return render_template(
        "progress.html",
        progress_stats=progress_stats,
        type_counts=type_counts,
        type_minutes=type_minutes,
        recent_workouts=recent_workouts,
        type_chart_labels=type_chart_labels,
        type_chart_counts=type_chart_counts,
        minutes_chart_labels=minutes_chart_labels,
        minutes_chart_values=minutes_chart_values,
        trend_chart_labels=trend_chart_labels,
        trend_chart_minutes=trend_chart_minutes,
    )


@app.route("/ranking")
def ranking():
    if not is_logged_in():
        return redirect(url_for("login"))

    current = current_user()
    if current is None:
        session.clear()
        return redirect(url_for("login"))

    users = User.query.filter_by(show_public_fitness=True).all()
    leaderboard = []

    for user in users:
        user_workouts = Workout.query.filter_by(user_id=user.id).all()

        total_workouts = len(user_workouts)
        total_minutes = sum(workout.duration for workout in user_workouts)
        workout_dates = [
            parse_workout_date(workout.date)
            for workout in user_workouts
            if parse_workout_date(workout.date) is not None
        ]

        if workout_dates:
            latest_workout_date = max(workout_dates)

            if latest_workout_date == date.today():
                last_workout_display = "Today"
            elif latest_workout_date == date.today() - timedelta(days=1):
                last_workout_display = "Yesterday"
            else:
                last_workout_display = latest_workout_date.strftime("%d %b %Y")
        else:
            last_workout_display = "No workouts"

        if user.show_public_profile:
            display_name = user.name
            avatar_filename = user.avatar_filename
            initials = "".join(part[0].upper() for part in user.name.split()[:2]) if user.name else "U"
        else:
            display_name = "Private User"
            avatar_filename = None
            initials = None

        leaderboard.append(
            {
                "user_id": user.id,
                "name": display_name,
                "workouts": total_workouts,
                "minutes": total_minutes,
                "streak": calculate_streak(user_workouts),
                "shared": True,
                "avatar_filename": avatar_filename,
                "profile_public": bool(user.show_public_profile),
                "fitness_public": bool(user.show_public_fitness),
                "initials": initials,
                "last_workout": last_workout_display,
            }
        )

    leaderboard = sorted(
        leaderboard,
        key=lambda user_data: user_data["minutes"],
        reverse=True
    )

    ranking_summary = {
        "total_ranked_users": len(leaderboard),
        "community_total_minutes": sum(user_data["minutes"] for user_data in leaderboard),
        "top_streak": max((user_data["streak"] for user_data in leaderboard), default=0),
        "top_user_name": leaderboard[0]["name"] if leaderboard else None,
    }

    current_user_rank = {
        "rank": None,
        "minutes": 0,
        "workouts": 0,
        "minutes_to_next_rank": 0,
    }

    for index, user_data in enumerate(leaderboard):
        if user_data["user_id"] == session["user_id"]:
            minutes_to_next_rank = 0

            if index > 0:
                minutes_to_next_rank = max(
                    0,
                    leaderboard[index - 1]["minutes"] - user_data["minutes"] + 1
                )

            current_user_rank = {
                "rank": index + 1,
                "minutes": user_data["minutes"],
                "workouts": user_data["workouts"],
                "minutes_to_next_rank": minutes_to_next_rank,
            }
            break

    community_disabled = not bool(current.show_public_fitness)

    return render_template(
        "ranking.html",
        leaderboard=leaderboard,
        ranking_summary=ranking_summary,
        current_user_rank=current_user_rank,
        community_disabled=community_disabled,
    )

@app.route("/plans")
def plans():
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    daily_minutes_goal = user.daily_minutes_goal or 20
    weight_goal_kg = user.weight_goal_kg
    today_text = date.today().isoformat()

    today_workouts = Workout.query.filter_by(
        user_id=user.id,
        date=today_text
    ).all()

    today_minutes = sum(workout.duration for workout in today_workouts)
    today_goal_percent = min(
        100,
        round(today_minutes / daily_minutes_goal * 100)
    )
    week_start = date.today() - timedelta(days=date.today().weekday())
    week_end = week_start + timedelta(days=6)
    week_workouts = Workout.query.filter_by(user_id=user.id).all()
    weekly_schedule = []

    for day_offset in range(7):
        schedule_date = week_start + timedelta(days=day_offset)
        schedule_date_text = schedule_date.isoformat()
        day_minutes = sum(
            workout.duration
            for workout in week_workouts
            if workout.date == schedule_date_text
        )
        is_today = schedule_date == date.today()

        if day_minutes > 0:
            status = "Completed"
        elif is_today:
            status = "Today"
        elif schedule_date.weekday() == 6:
            status = "Rest"
        elif schedule_date > date.today() and schedule_date <= week_end:
            status = "Planned"
        else:
            status = "Rest"

        weekly_schedule.append({
            "day_name": schedule_date.strftime("%A"),
            "date_number": schedule_date.day,
            "date": schedule_date_text,
            "is_today": is_today,
            "minutes": day_minutes,
            "status": status,
        })

    saved_recommendation = PlanRecommendation.query.filter_by(
        user_id=user.id
    ).first()
    recommended_weekly_structure = []
    recommendation_badges = []

    if saved_recommendation and saved_recommendation.weekly_structure_json:
        try:
            parsed_structure = json.loads(
                saved_recommendation.weekly_structure_json
            )

            if isinstance(parsed_structure, list):
                recommended_weekly_structure = parsed_structure
        except json.JSONDecodeError:
            recommended_weekly_structure = []

    if saved_recommendation and saved_recommendation.plan_badges_json:
        try:
            parsed_badges = json.loads(saved_recommendation.plan_badges_json)

            if isinstance(parsed_badges, list):
                recommendation_badges = parsed_badges
        except json.JSONDecodeError:
            recommendation_badges = []

    return render_template(
        "plans.html",
        email=session["user_email"],
        daily_minutes_goal=daily_minutes_goal,
        weight_goal_kg=weight_goal_kg,
        today_minutes=today_minutes,
        today_goal_percent=today_goal_percent,
        weekly_schedule=weekly_schedule,
        saved_recommendation=saved_recommendation,
        recommended_weekly_structure=recommended_weekly_structure,
        recommendation_badges=recommendation_badges,
    )


@app.route("/plans/goals", methods=["POST"])
def save_plan_goals():
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    daily_minutes_text = request.form.get("daily_minutes_goal", "").strip()
    weight_goal_text = request.form.get("weight_goal_kg", "").strip()

    try:
        daily_minutes_goal = int(daily_minutes_text)
    except ValueError:
        flash("Daily minutes goal must be a positive whole number.", "danger")
        return redirect(url_for("plans"))

    if daily_minutes_goal <= 0:
        flash("Daily minutes goal must be a positive whole number.", "danger")
        return redirect(url_for("plans"))

    weight_goal_kg = None

    if weight_goal_text:
        try:
            weight_goal_kg = float(weight_goal_text)
        except ValueError:
            flash("Weight goal must be a positive number.", "danger")
            return redirect(url_for("plans"))

        if weight_goal_kg <= 0:
            flash("Weight goal must be a positive number.", "danger")
            return redirect(url_for("plans"))

    user.daily_minutes_goal = daily_minutes_goal
    user.weight_goal_kg = weight_goal_kg
    db.session.commit()

    flash("Plan goals saved successfully.", "success")
    return redirect(url_for("plans"))


@app.route("/plans/recommendation", methods=["POST"])
def save_plan_recommendation():
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    main_goal = request.form.get("main_goal", "").strip()
    fitness_level = request.form.get("fitness_level", "").strip()
    training_days = request.form.get("training_days", "").strip()
    session_length = request.form.get("session_length", "").strip()
    limitation = request.form.get("limitation", "").strip()
    equipment_access = request.form.get("equipment_access", "").strip()
    training_preference = request.form.get("training_preference", "").strip()

    allowed_goals = [
        "build_strength",
        "improve_cardio",
        "lose_weight",
        "improve_flexibility",
        "build_consistency",
    ]
    allowed_levels = ["beginner", "intermediate", "advanced"]
    allowed_training_days = ["1", "2", "3", "4", "5", "6"]
    allowed_session_lengths = ["15", "20", "30", "45", "60"]
    allowed_limitations = [
        "none",
        "knee_discomfort",
        "back_discomfort",
        "shoulder_discomfort",
        "low_energy",
    ]
    allowed_equipment = [
        "gym",
        "home",
        "outdoor",
        "bodyweight_only",
    ]
    allowed_preferences = [
        "structured",
        "short_simple",
        "low_impact",
        "challenge",
        "balanced",
    ]

    if main_goal not in allowed_goals:
        flash("Please choose a valid main goal.", "danger")
        return redirect(url_for("plans"))

    if fitness_level not in allowed_levels:
        flash("Please choose a valid fitness level.", "danger")
        return redirect(url_for("plans"))

    if training_days not in allowed_training_days:
        flash("Please choose a valid number of training days.", "danger")
        return redirect(url_for("plans"))

    if session_length not in allowed_session_lengths:
        flash("Please choose a valid session length.", "danger")
        return redirect(url_for("plans"))

    if limitation not in allowed_limitations:
        flash("Please choose a valid limitation option.", "danger")
        return redirect(url_for("plans"))

    if equipment_access not in allowed_equipment:
        flash("Please choose a valid equipment access option.", "danger")
        return redirect(url_for("plans"))

    if training_preference not in allowed_preferences:
        flash("Please choose a valid training preference.", "danger")
        return redirect(url_for("plans"))

    recommendation = build_plan_recommendation(
        main_goal,
        fitness_level,
        training_days,
        session_length,
        limitation,
        equipment_access,
        training_preference
    )

    saved_recommendation = PlanRecommendation.query.filter_by(
        user_id=user.id
    ).first()

    if saved_recommendation is None:
        saved_recommendation = PlanRecommendation(user_id=user.id)
        db.session.add(saved_recommendation)

    saved_recommendation.main_goal = main_goal
    saved_recommendation.fitness_level = fitness_level
    saved_recommendation.training_days = int(training_days)
    saved_recommendation.session_length = int(session_length)
    saved_recommendation.limitation = limitation
    saved_recommendation.equipment_access = equipment_access
    saved_recommendation.training_preference = training_preference
    saved_recommendation.recommended_plan = recommendation["recommended_plan"]
    saved_recommendation.recommendation_reason = recommendation["recommendation_reason"]
    saved_recommendation.weekly_structure_json = json.dumps(
        recommendation["weekly_structure"]
    )
    saved_recommendation.plan_focus = recommendation.get("plan_focus")
    saved_recommendation.suggested_intensity = recommendation.get("suggested_intensity")
    saved_recommendation.plan_badges_json = json.dumps(
        recommendation.get("plan_badges", [])
    )

    db.session.commit()

    flash("Personalised plan recommendation saved.", "success")
    return redirect(url_for("plans"))


@app.route("/plans/recommendation/clear", methods=["POST"])
def clear_plan_recommendation():
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    saved_recommendation = PlanRecommendation.query.filter_by(
        user_id=user.id
    ).first()

    if saved_recommendation is not None:
        db.session.delete(saved_recommendation)
        db.session.commit()
        flash("Personalised plan recommendation cleared.", "success")

    return redirect(url_for("plans"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


if __name__ == "__main__":
    ensure_database_ready()
    app.run(debug=True)
