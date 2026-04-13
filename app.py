import os
from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
app.secret_key = "dev-secret-key"

DEMO_EMAIL = "demo@fittrack.com"
DEMO_PASSWORD = "password123"


SAMPLE_RUNS = [
    {
        "id": 1,
        "title": "Kings Park Morning Run",
        "date": "2026-04-10",
        "distance_km": 5.1,
        "duration_min": 27.8,
        "lap_times_sec": [320, 315, 330, 318, 325],
        "path": [
            {"lat": -31.9605, "lng": 115.8320},
            {"lat": -31.9590, "lng": 115.8340},
            {"lat": -31.9575, "lng": 115.8365},
            {"lat": -31.9555, "lng": 115.8385},
            {"lat": -31.9538, "lng": 115.8400},
            {"lat": -31.9525, "lng": 115.8380},
            {"lat": -31.9535, "lng": 115.8350},
            {"lat": -31.9555, "lng": 115.8330},
            {"lat": -31.9580, "lng": 115.8318},
            {"lat": -31.9605, "lng": 115.8320},
        ],
    },
    {
        "id": 2,
        "title": "Riverside Easy Run",
        "date": "2026-04-07",
        "distance_km": 4.2,
        "duration_min": 24.1,
        "lap_times_sec": [350, 342, 338, 330],
        "path": [
            {"lat": -31.9695, "lng": 115.8500},
            {"lat": -31.9682, "lng": 115.8525},
            {"lat": -31.9668, "lng": 115.8550},
            {"lat": -31.9650, "lng": 115.8570},
            {"lat": -31.9638, "lng": 115.8550},
            {"lat": -31.9650, "lng": 115.8520},
            {"lat": -31.9670, "lng": 115.8498},
            {"lat": -31.9695, "lng": 115.8500},
        ],
    },
]


def build_lap_leaderboard(runs):
    laps = []

    for run in runs:
        for index, lap_time in enumerate(run["lap_times_sec"], start=1):
            laps.append(
                {
                    "run_title": run["title"],
                    "date": run["date"],
                    "lap_number": index,
                    "lap_time_sec": lap_time,
                }
            )

    laps.sort(key=lambda x: x["lap_time_sec"])
    return laps[:10]


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
    if "user_email" not in session:
        return redirect(url_for("login"))

    lap_leaderboard = build_lap_leaderboard(SAMPLE_RUNS)
    maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyDg7htjB8064ZdvXDiLJNCfDSMhe1Jeass")

    return render_template(
        "dashboard.html",
        email=session["user_email"],
        runs=SAMPLE_RUNS,
        lap_leaderboard=lap_leaderboard,
        maps_api_key=maps_api_key,
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)