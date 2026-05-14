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

    # Privacy / visibility settings
    show_public_profile = db.Column(db.Boolean, nullable=False, default=True)
    show_public_fitness = db.Column(db.Boolean, nullable=False, default=True)

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


class WorkoutSet(db.Model):
    __tablename__ = "workout_sets"

    id = db.Column(db.Integer, primary_key=True)
    workout_id = db.Column(db.Integer, db.ForeignKey("workouts.id"), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercises.id"), nullable=False)

    set_number = db.Column(db.Integer, nullable=False)
    reps = db.Column(db.Integer, nullable=False)
    weight_kg = db.Column(db.Float, nullable=False)

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


def current_user():
    if "user_id" not in session:
        return None

    return db.session.get(User, session["user_id"])


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

        if "privacy_settings_present" in request.form:
            user.show_public_profile = request.form.get("show_public_profile") == "on"
            user.show_public_fitness = request.form.get("show_public_fitness") == "on"

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

    return render_template(
        "add_workout.html",
        muscle_groups=MUSCLE_GROUPS,
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
        db.or_(
            Exercise.user_id == None,
            Exercise.user_id == user.id
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

    name = (data.get("name") or "").strip()
    muscle_group = (data.get("muscle_group") or "").strip()

    if not name:
        return jsonify({"error": "Exercise name is required"}), 400

    if muscle_group not in MUSCLE_GROUPS:
        return jsonify({"error": f"muscle_group must be one of: {', '.join(MUSCLE_GROUPS)}"}), 400

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

    try:
        started_at = datetime.fromisoformat(data["started_at"])
        finished_at = datetime.fromisoformat(data["finished_at"])
    except (KeyError, ValueError):
        return jsonify({"error": "started_at and finished_at must be valid ISO datetime strings"}), 400

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
            reps = int(raw_set["reps"])
            weight_kg = float(raw_set["weight_kg"])
        except (KeyError, ValueError, TypeError):
            return jsonify({"error": f"Set {index} is missing or has invalid fields"}), 400

        if reps <= 0:
            return jsonify({"error": f"Set {index}: reps must be greater than 0"}), 400

        if weight_kg < 0:
            return jsonify({"error": f"Set {index}: weight_kg cannot be negative"}), 400

        exercise = Exercise.query.filter(
            Exercise.id == exercise_id,
            db.or_(Exercise.user_id == None, Exercise.user_id == user.id)
        ).first()

        if exercise is None:
            return jsonify({"error": f"Set {index}: exercise_id {exercise_id} not found"}), 404

        validated_sets.append({
            "exercise": exercise,
            "set_number": set_number,
            "reps": reps,
            "weight_kg": weight_kg,
        })

    muscle_groups_trained = list(dict.fromkeys(
        saved_set["exercise"].muscle_group
        for saved_set in validated_sets
    ))

    workout_type = ", ".join(muscle_groups_trained)

    weights = [saved_set["weight_kg"] for saved_set in validated_sets]
    average_weight = sum(weights) / len(weights)

    if average_weight == 0:
        intensity = "Low"
    elif average_weight < 40:
        intensity = "Low"
    elif average_weight < 80:
        intensity = "Medium"
    else:
        intensity = "High"

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
    db.session.flush()

    for saved_set in validated_sets:
        workout_set = WorkoutSet(
            workout_id=new_workout.id,
            exercise_id=saved_set["exercise"].id,
            set_number=saved_set["set_number"],
            reps=saved_set["reps"],
            weight_kg=saved_set["weight_kg"],
        )

        db.session.add(workout_set)

    db.session.commit()

    total_volume_kg = sum(
        saved_set["reps"] * saved_set["weight_kg"]
        for saved_set in validated_sets
    )

    sets_per_exercise = {}

    for saved_set in validated_sets:
        exercise_name = saved_set["exercise"].name
        sets_per_exercise[exercise_name] = sets_per_exercise.get(exercise_name, 0) + 1

    return jsonify({
        "workout_id": new_workout.id,
        "date": new_workout.date,
        "type": workout_type,
        "duration_minutes": duration_minutes,
        "intensity": intensity,
        "total_sets": len(validated_sets),
        "total_volume_kg": round(total_volume_kg, 1),
        "exercises": sets_per_exercise,
        "muscle_groups": muscle_groups_trained,
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

    users = User.query.filter_by(show_public_fitness=True).all()
    leaderboard = []

    for user in users:
        user_workouts = Workout.query.filter_by(user_id=user.id).all()

        total_workouts = len(user_workouts)
        total_minutes = sum(workout.duration for workout in user_workouts)

        if user.show_public_profile:
            display_name = user.name
            avatar_filename = user.avatar_filename
        else:
            display_name = "Private User"
            avatar_filename = None

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

    return render_template(
        "ranking.html",
        leaderboard=leaderboard,
        ranking_summary=ranking_summary,
        current_user_rank=current_user_rank
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
