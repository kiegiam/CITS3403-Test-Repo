import os
from datetime import date, datetime

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.secret_key = "dev-secret-key"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///fittrack.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# User-uploaded avatar settings
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
app.config["ALLOWED_IMAGE_EXTENSIONS"] = {"png", "jpg", "jpeg", "gif"}

db = SQLAlchemy(app)


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

    workouts = db.relationship(
        "Workout",
        backref="owner",
        lazy=True,
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User {self.email}>"


class Workout(db.Model):
    __tablename__ = "workouts"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    intensity = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text, nullable=True)

    # Populated automatically from the live timer when a workout is finished.
    # NULL means the workout was logged via the old manual form.
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


# ---------------------------------------------------------------------------
# Exercise catalogue
# ---------------------------------------------------------------------------
# Built-in exercises have user_id = NULL.
# Custom exercises created by a user have user_id = that user's id.
# ---------------------------------------------------------------------------

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

class Exercise(db.Model):
    __tablename__ = "exercises"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    muscle_group = db.Column(db.String(50), nullable=False)

    # NULL = built-in exercise visible to everyone.
    # Set to a user id = custom exercise visible only to that user.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

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
        }


# ---------------------------------------------------------------------------
# Individual sets logged during a workout
# ---------------------------------------------------------------------------

class WorkoutSet(db.Model):
    __tablename__ = "workout_sets"

    id = db.Column(db.Integer, primary_key=True)
    workout_id = db.Column(db.Integer, db.ForeignKey("workouts.id"), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercises.id"), nullable=False)

    set_number = db.Column(db.Integer, nullable=False)   # 1, 2, 3 …
    reps = db.Column(db.Integer, nullable=False)
    weight_kg = db.Column(db.Float, nullable=False)       # 0 for bodyweight

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

        # ------------------------------------------------------------------ #
        # Migrate users table: add avatar_filename if missing (legacy DBs)    #
        # ------------------------------------------------------------------ #
        user_columns = [
            col[1] for col in
            db.session.execute(text("PRAGMA table_info(users)")).fetchall()
        ]
        if "avatar_filename" not in user_columns:
            db.session.execute(
                text("ALTER TABLE users ADD COLUMN avatar_filename VARCHAR(255)")
            )
            db.session.commit()

        # ------------------------------------------------------------------ #
        # Migrate workouts table: add started_at / finished_at if missing     #
        # ------------------------------------------------------------------ #
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

        # ------------------------------------------------------------------ #
        # Seed built-in exercise catalogue (runs once; skipped if populated)  #
        # ------------------------------------------------------------------ #
        if Exercise.query.filter_by(user_id=None).count() == 0:
            builtin_exercises = [
                # Chest
                Exercise(name="Bench Press",         muscle_group="Chest"),
                Exercise(name="Incline Bench Press", muscle_group="Chest"),
                Exercise(name="Dumbbell Fly",        muscle_group="Chest"),
                Exercise(name="Push-Up",             muscle_group="Chest"),
                Exercise(name="Cable Crossover",     muscle_group="Chest"),
                # Back
                Exercise(name="Deadlift",            muscle_group="Back"),
                Exercise(name="Pull-Up",             muscle_group="Back"),
                Exercise(name="Barbell Row",         muscle_group="Back"),
                Exercise(name="Lat Pulldown",        muscle_group="Back"),
                Exercise(name="Seated Cable Row",    muscle_group="Back"),
                # Shoulders
                Exercise(name="Overhead Press",      muscle_group="Shoulders"),
                Exercise(name="Lateral Raise",       muscle_group="Shoulders"),
                Exercise(name="Front Raise",         muscle_group="Shoulders"),
                Exercise(name="Arnold Press",        muscle_group="Shoulders"),
                Exercise(name="Rear Delt Fly",       muscle_group="Shoulders"),
                # Biceps
                Exercise(name="Barbell Curl",        muscle_group="Biceps"),
                Exercise(name="Dumbbell Curl",       muscle_group="Biceps"),
                Exercise(name="Hammer Curl",         muscle_group="Biceps"),
                Exercise(name="Preacher Curl",       muscle_group="Biceps"),
                Exercise(name="Cable Curl",          muscle_group="Biceps"),
                # Triceps
                Exercise(name="Tricep Pushdown",              muscle_group="Triceps"),
                Exercise(name="Skull Crusher",                muscle_group="Triceps"),
                Exercise(name="Overhead Tricep Extension",    muscle_group="Triceps"),
                Exercise(name="Close-Grip Bench Press",       muscle_group="Triceps"),
                Exercise(name="Dips",                         muscle_group="Triceps"),
                # Legs
                Exercise(name="Squat",               muscle_group="Legs"),
                Exercise(name="Leg Press",           muscle_group="Legs"),
                Exercise(name="Romanian Deadlift",   muscle_group="Legs"),
                Exercise(name="Leg Curl",            muscle_group="Legs"),
                Exercise(name="Leg Extension",       muscle_group="Legs"),
                Exercise(name="Calf Raise",          muscle_group="Legs"),
                Exercise(name="Lunges",              muscle_group="Legs"),
                # Core
                Exercise(name="Plank",               muscle_group="Core"),
                Exercise(name="Crunch",              muscle_group="Core"),
                Exercise(name="Hanging Leg Raise",   muscle_group="Core"),
                Exercise(name="Russian Twist",       muscle_group="Core"),
                Exercise(name="Ab Wheel Rollout",    muscle_group="Core"),
                # Cardio
                Exercise(name="Treadmill Run",       muscle_group="Cardio"),
                Exercise(name="Cycling",             muscle_group="Cardio"),
                Exercise(name="Rowing Machine",      muscle_group="Cardio"),
                Exercise(name="Jump Rope",           muscle_group="Cardio"),
                Exercise(name="Stair Climber",       muscle_group="Cardio"),
            ]
            db.session.add_all(builtin_exercises)
            db.session.commit()

        # ------------------------------------------------------------------ #
        # Seed demo user and sample workouts                                  #
        # ------------------------------------------------------------------ #
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


def current_user():
    if "user_id" not in session:
        return None

    return db.session.get(User, session["user_id"])


def allowed_image(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_IMAGE_EXTENSIONS"]
    )


def user_to_profile_dict(user):
    return {
        "name": user.name,
        "email": user.email,
        "goal": user.goal or "No goal set yet.",
        "member_since": user.member_since or "Unknown",
        "location": user.location or "Not set",
        "avatar_filename": user.avatar_filename,
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


def get_statistics(user):
    user_workouts = Workout.query.filter_by(user_id=user.id).all()

    total_workouts = len(user_workouts)
    total_minutes = sum(workout.duration for workout in user_workouts)

    current_streak = 6

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
        "current_streak": 6,
        "most_common_type": most_common_type,
    }

    return progress_stats, type_counts, type_minutes


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        goal = request.form.get("goal", "").strip()
        location = request.form.get("location", "").strip()

        if not name or not email or not password:
            flash("Name, email, and password are required.")
            return render_template("register.html")

        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("An account with that email already exists.")
            return render_template("register.html")

        new_user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            goal=goal or "Stay consistent",
            member_since=date.today().strftime("%B %Y"),
            location=location or "Not set",
            avatar_filename=None,
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
        name = request.form.get("name", "").strip()
        goal = request.form.get("goal", "").strip()
        location = request.form.get("location", "").strip()
        avatar_file = request.files.get("avatar")

        if not name:
            flash("Name cannot be empty.")
            return render_template(
                "edit_profile.html",
                profile=user_to_profile_dict(user)
            )

        user.name = name
        user.goal = goal or "Stay consistent"
        user.location = location or "Not set"

        if avatar_file and avatar_file.filename:
            if not allowed_image(avatar_file.filename):
                flash("Avatar must be an image file: png, jpg, jpeg, or gif.")
                return render_template(
                    "edit_profile.html",
                    profile=user_to_profile_dict(user)
                )

            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

            original_filename = secure_filename(avatar_file.filename)
            file_extension = original_filename.rsplit(".", 1)[1].lower()

            avatar_filename = f"user_{user.id}_avatar.{file_extension}"
            avatar_path = os.path.join(app.config["UPLOAD_FOLDER"], avatar_filename)

            avatar_file.save(avatar_path)
            user.avatar_filename = avatar_filename

        db.session.commit()

        flash("Profile updated successfully.")
        return redirect(url_for("profile"))

    return render_template(
        "edit_profile.html",
        profile=user_to_profile_dict(user)
    )


@app.route("/workouts")
def workouts():
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    workout_objects = (
        Workout.query
        .filter_by(user_id=user.id)
        .order_by(Workout.date.desc(), Workout.id.desc())
        .all()
    )

    workout_list = [
        workout_to_dict(workout)
        for workout in workout_objects
    ]

    return render_template(
        "workouts.html",
        workouts=workout_list
    )


@app.route("/workouts/add")
def add_workout():
    """Landing page for the new workout flow.

    Renders the muscle-group / exercise selector with a live timer.
    The actual saving is handled by POST /workouts/finish.
    """
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    return render_template(
        "add_workout.html",
        muscle_groups=MUSCLE_GROUPS,
    )


# ---------------------------------------------------------------------------
# API: exercise catalogue
# ---------------------------------------------------------------------------

@app.route("/api/exercises")
def api_exercises():
    """Return exercises for a given muscle group as JSON.

    Query params:
        muscle_group  – required, e.g. "Chest"

    Returns built-in exercises (user_id IS NULL) plus the current user's
    custom exercises for that muscle group.
    """
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
        db.or_(
            Exercise.user_id == None,   # built-ins
            Exercise.user_id == user.id # user's own custom exercises
        )
    ).order_by(Exercise.name).all()

    return jsonify([ex.to_dict() for ex in exercises])


@app.route("/api/exercises", methods=["POST"])
def api_add_exercise():
    """Create a custom exercise for the current user.

    Expects JSON body:
        { "name": "...", "muscle_group": "..." }
    """
    if not is_logged_in():
        return jsonify({"error": "Unauthorised"}), 401

    user = current_user()
    if user is None:
        return jsonify({"error": "Unauthorised"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    name = (data.get("name") or "").strip()
    muscle_group = (data.get("muscle_group") or "").strip()

    if not name:
        return jsonify({"error": "Exercise name is required"}), 400

    if muscle_group not in MUSCLE_GROUPS:
        return jsonify({"error": f"muscle_group must be one of: {', '.join(MUSCLE_GROUPS)}"}), 400

    # Prevent duplicates: same name + muscle group for this user or built-ins
    duplicate = Exercise.query.filter(
        Exercise.name.ilike(name),
        Exercise.muscle_group == muscle_group,
        db.or_(Exercise.user_id == None, Exercise.user_id == user.id)
    ).first()

    if duplicate:
        return jsonify({"error": "An exercise with that name already exists in this muscle group"}), 409

    new_exercise = Exercise(
        name=name,
        muscle_group=muscle_group,
        user_id=user.id,
    )
    db.session.add(new_exercise)
    db.session.commit()

    return jsonify(new_exercise.to_dict()), 201


# ---------------------------------------------------------------------------
# Finish workout: save sets + calculate duration from timer
# ---------------------------------------------------------------------------

@app.route("/workouts/finish", methods=["POST"])
def finish_workout():
    """Receive the completed workout from the frontend and persist it.

    Expects JSON body:
    {
        "started_at":  "<ISO 8601 string>",   // e.g. "2026-05-06T09:00:00"
        "finished_at": "<ISO 8601 string>",
        "notes":       "optional free text",
        "sets": [
            {
                "exercise_id": 3,
                "set_number":  1,
                "reps":        10,
                "weight_kg":   80.0
            },
            ...
        ]
    }

    The workout's `type` is derived from the muscle groups exercised,
    `intensity` from average weight lifted, and `duration` from the timer.
    """
    if not is_logged_in():
        return jsonify({"error": "Unauthorised"}), 401

    user = current_user()
    if user is None:
        return jsonify({"error": "Unauthorised"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    # ---- parse timestamps ------------------------------------------------ #
    try:
        started_at  = datetime.fromisoformat(data["started_at"])
        finished_at = datetime.fromisoformat(data["finished_at"])
    except (KeyError, ValueError):
        return jsonify({"error": "started_at and finished_at must be valid ISO datetime strings"}), 400

    if finished_at <= started_at:
        return jsonify({"error": "finished_at must be after started_at"}), 400

    duration_seconds = int((finished_at - started_at).total_seconds())
    duration_minutes = max(1, round(duration_seconds / 60))

    # ---- validate sets --------------------------------------------------- #
    raw_sets = data.get("sets", [])
    if not raw_sets:
        return jsonify({"error": "At least one set is required"}), 400

    validated_sets = []
    for i, s in enumerate(raw_sets):
        try:
            exercise_id = int(s["exercise_id"])
            set_number  = int(s["set_number"])
            reps        = int(s["reps"])
            weight_kg   = float(s["weight_kg"])
        except (KeyError, ValueError, TypeError):
            return jsonify({"error": f"Set {i} is missing or has invalid fields"}), 400

        if reps <= 0:
            return jsonify({"error": f"Set {i}: reps must be greater than 0"}), 400
        if weight_kg < 0:
            return jsonify({"error": f"Set {i}: weight_kg cannot be negative"}), 400

        # Confirm the exercise exists and belongs to this user or is built-in
        exercise = Exercise.query.filter(
            Exercise.id == exercise_id,
            db.or_(Exercise.user_id == None, Exercise.user_id == user.id)
        ).first()

        if exercise is None:
            return jsonify({"error": f"Set {i}: exercise_id {exercise_id} not found"}), 404

        validated_sets.append({
            "exercise":   exercise,
            "set_number": set_number,
            "reps":       reps,
            "weight_kg":  weight_kg,
        })

    # ---- derive workout metadata ----------------------------------------- #
    # Type: comma-joined unique muscle groups that were trained
    muscle_groups_trained = list(dict.fromkeys(
        s["exercise"].muscle_group for s in validated_sets
    ))
    workout_type = ", ".join(muscle_groups_trained)

    # Intensity: based on average weight across all sets
    weights = [s["weight_kg"] for s in validated_sets]
    avg_weight = sum(weights) / len(weights)

    if avg_weight == 0:
        intensity = "Low"        # bodyweight only
    elif avg_weight < 40:
        intensity = "Low"
    elif avg_weight < 80:
        intensity = "Medium"
    else:
        intensity = "High"

    notes = (data.get("notes") or "").strip() or "No notes added."

    # ---- persist --------------------------------------------------------- #
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
    db.session.flush()  # get new_workout.id before committing

    for s in validated_sets:
        workout_set = WorkoutSet(
            workout_id=new_workout.id,
            exercise_id=s["exercise"].id,
            set_number=s["set_number"],
            reps=s["reps"],
            weight_kg=s["weight_kg"],
        )
        db.session.add(workout_set)

    db.session.commit()

    # ---- build summary for the frontend ---------------------------------- #
    total_volume_kg = sum(s["reps"] * s["weight_kg"] for s in validated_sets)
    sets_per_exercise = {}
    for s in validated_sets:
        ex_name = s["exercise"].name
        sets_per_exercise[ex_name] = sets_per_exercise.get(ex_name, 0) + 1

    return jsonify({
        "workout_id":       new_workout.id,
        "date":             new_workout.date,
        "type":             workout_type,
        "duration_minutes": duration_minutes,
        "intensity":        intensity,
        "total_sets":       len(validated_sets),
        "total_volume_kg":  round(total_volume_kg, 1),
        "exercises":        sets_per_exercise,
        "muscle_groups":    muscle_groups_trained,
    }), 201


@app.route("/workouts/<int:workout_id>/edit", methods=["GET", "POST"])
def edit_workout(workout_id):
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

    if request.method == "POST":
        date_value = request.form.get("date", "").strip()
        workout_type = request.form.get("type", "").strip()
        duration = request.form.get("duration", "").strip()
        intensity = request.form.get("intensity", "").strip()
        notes = request.form.get("notes", "").strip()

        if not date_value or not workout_type or not duration or not intensity:
            flash("Please complete all required fields.")
            return render_template(
                "edit_workout.html",
                workout=workout
            )

        try:
            datetime.strptime(date_value, "%Y-%m-%d")
        except ValueError:
            flash("Date must use the format YYYY-MM-DD.")
            return render_template(
                "edit_workout.html",
                workout=workout
            )

        try:
            duration_value = int(duration)
        except ValueError:
            flash("Duration must be a number.")
            return render_template(
                "edit_workout.html",
                workout=workout
            )

        if duration_value <= 0:
            flash("Duration must be greater than 0.")
            return render_template(
                "edit_workout.html",
                workout=workout
            )

        workout.date = date_value
        workout.type = workout_type
        workout.duration = duration_value
        workout.intensity = intensity
        workout.notes = notes or "No notes added."

        db.session.commit()

        flash("Workout updated successfully.")
        return redirect(url_for("workouts"))

    return render_template(
        "edit_workout.html",
        workout=workout
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

    return render_template(
        "progress.html",
        progress_stats=progress_stats,
        type_counts=type_counts,
        type_minutes=type_minutes,
        recent_workouts=recent_workouts,
    )


@app.route("/ranking")
def ranking():
    if not is_logged_in():
        return redirect(url_for("login"))

    users = User.query.all()
    leaderboard = []

    for user in users:
        user_workouts = Workout.query.filter_by(user_id=user.id).all()

        total_workouts = len(user_workouts)
        total_minutes = sum(workout.duration for workout in user_workouts)

        leaderboard.append(
            {
                "name": user.name,
                "workouts": total_workouts,
                "minutes": total_minutes,
                "streak": 6,
                "shared": True,
            }
        )

    leaderboard = sorted(
        leaderboard,
        key=lambda user_data: user_data["minutes"],
        reverse=True
    )

    return render_template(
        "ranking.html",
        leaderboard=leaderboard
    )


@app.route("/plans")
def plans():
    if not is_logged_in():
        return redirect(url_for("login"))

    return render_template(
        "plans.html",
        email=session["user_email"]
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


if __name__ == "__main__":
    ensure_database_ready()
    app.run(debug=True)
