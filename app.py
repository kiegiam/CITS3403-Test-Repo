from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
app.secret_key = "dev-secret-key"

DEMO_EMAIL = "demo@fittrack.com"
DEMO_PASSWORD = "password123"

# Temporary demo data. This can be replaced with a database later.
DEMO_PROFILE = {
    "name": "Demo User",
    "email": DEMO_EMAIL,
    "goal": "Stay consistent",
    "member_since": "April 2026",
    "location": "Perth, WA",
}

WORKOUTS = [
    {
        "date": "2026-04-20",
        "type": "Running",
        "duration": 30,
        "intensity": "Medium",
        "notes": "Felt good and kept a steady pace.",
    },
    {
        "date": "2026-04-21",
        "type": "Gym",
        "duration": 60,
        "intensity": "High",
        "notes": "Leg day with squats and lunges.",
    },
    {
        "date": "2026-04-23",
        "type": "Swimming",
        "duration": 45,
        "intensity": "Medium",
        "notes": "Easy pace recovery session.",
    },
    {
        "date": "2026-04-24",
        "type": "Cycling",
        "duration": 40,
        "intensity": "Low",
        "notes": "Light cardio after class.",
    },
]


def login_required():
    return "user_email" in session


def get_statistics():
    total_workouts = len(WORKOUTS)
    total_minutes = sum(workout["duration"] for workout in WORKOUTS)
    current_streak = 6

    return {
        "total_workouts": total_workouts,
        "total_minutes": total_minutes,
        "current_streak": current_streak,
    }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if email == DEMO_EMAIL and password == DEMO_PASSWORD:
            session["user_email"] = email
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect(url_for("login"))

    recent_workouts = WORKOUTS[-3:][::-1]
    statistics = get_statistics()

    return render_template(
        "dashboard.html",
        email=session["user_email"],
        recent_workouts=recent_workouts,
        statistics=statistics,
    )


@app.route("/profile")
def profile():
    if not login_required():
        return redirect(url_for("login"))

    statistics = get_statistics()

    return render_template(
        "profile.html",
        profile=DEMO_PROFILE,
        statistics=statistics,
    )


@app.route("/workouts")
def workouts():
    if not login_required():
        return redirect(url_for("login"))

    return render_template("workouts.html", workouts=WORKOUTS[::-1])


@app.route("/workouts/add", methods=["GET", "POST"])
def add_workout():
    if not login_required():
        return redirect(url_for("login"))

    if request.method == "POST":
        date = request.form.get("date", "").strip()
        workout_type = request.form.get("type", "").strip()
        duration = request.form.get("duration", "").strip()
        intensity = request.form.get("intensity", "").strip()
        notes = request.form.get("notes", "").strip()

        if not date or not workout_type or not duration or not intensity:
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

        WORKOUTS.append(
            {
                "date": date,
                "type": workout_type,
                "duration": duration_value,
                "intensity": intensity,
                "notes": notes or "No notes added.",
            }
        )

        flash("Workout added successfully.")
        return redirect(url_for("workouts"))

    return render_template("add_workout.html")

@app.route('/plans')
def plans():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('plans.html', email=session['email'])


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)
