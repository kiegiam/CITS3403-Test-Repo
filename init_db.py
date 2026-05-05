from datetime import date

from werkzeug.security import generate_password_hash

from app import app, db, User, Workout


with app.app_context():
    db.create_all()

    existing_demo = User.query.filter_by(email="demo@fittrack.com").first()

    if not existing_demo:
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

        print("Database created and demo user seeded.")
    else:
        print("Database already exists and demo user already present.")