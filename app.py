from datetime import date

from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "dev-secret-key"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///fittrack.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    def __repr__(self):
        return f"<Workout {self.type} on {self.date}>"


def is_logged_in():
    return "user_id" in session


def current_user():
    if "user_id" not in session:
        return None
    return db.session.get(User, session["user_id"])


def user_to_profile_dict(user):
    return {
        "name": user.name,
        "email": user.email,
        "goal": user.goal or "No goal set yet.",
        "member_since": user.member_since or "Unknown",
        "location": user.location or "Not set",
    }


def workout_to_dict(workout):
    return {
        "date": workout.date,
        "type": workout.type,
        "duration": workout.duration,
        "intensity": workout.intensity,
        "notes": workout.notes or "No notes added.",
    }


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

    recent_workouts = [workout_to_dict(workout) for workout in recent_workout_objects]
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

        if not name:
            flash("Name cannot be empty.")
            return render_template("edit_profile.html", profile=user_to_profile_dict(user))

        user.name = name
        user.goal = goal or "Stay consistent"
        user.location = location or "Not set"

        db.session.commit()
        flash("Profile updated successfully.")
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

    workout_objects = (
        Workout.query
        .filter_by(user_id=user.id)
        .order_by(Workout.date.desc(), Workout.id.desc())
        .all()
    )

    workout_list = [workout_to_dict(workout) for workout in workout_objects]
    return render_template("workouts.html", workouts=workout_list)


@app.route("/workouts/add", methods=["GET", "POST"])
def add_workout():
    if not is_logged_in():
        return redirect(url_for("login"))

    user = current_user()
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    if request.method == "POST":
        date_value = request.form.get("date", "").strip()
        workout_type = request.form.get("type", "").strip()
        duration = request.form.get("duration", "").strip()
        intensity = request.form.get("intensity", "").strip()
        notes = request.form.get("notes", "").strip()

        if not date_value or not workout_type or not duration or not intensity:
            flash("Please complete all required fields.")
            return render_template("add_workout.html")

        try:
            duration_value = int(duration)
        except ValueError:
            flash("Duration must be a number.")
            return render_template("add_workout.html")

        if duration_value <= 0:
            flash("Duration must be greater than 0.")
            return render_template("add_workout.html")

        new_workout = Workout(
            date=date_value,
            type=workout_type,
            duration=duration_value,
            intensity=intensity,
            notes=notes or "No notes added.",
            user_id=user.id,
        )

        db.session.add(new_workout)
        db.session.commit()

        flash("Workout added successfully.")
        return redirect(url_for("workouts"))

    return render_template("add_workout.html")


@app.route("/plans")
def plans():
    if not is_logged_in():
        return redirect(url_for("login"))

    return render_template("plans.html", email=session["user_email"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)