"""
FitTrack — Unit Tests
=====================
Run with:  python -m pytest test_unit.py -v

Tests cover:
    - User registration and login
    - Workout CRUD (add, edit, delete)
    - Progress statistics calculation
    - Streak calculation
    - CSRF protection on forms
    - Access control (login required)
"""

import os
import pytest
from datetime import date, timedelta

# Use an in-memory SQLite database for tests so the real DB is never touched.
os.environ["SECRET_KEY"] = "test-secret-key"

from app import app, db, User, Workout, calculate_streak
from werkzeug.security import generate_password_hash


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Flask test client with an isolated in-memory database."""
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["WTF_CSRF_ENABLED"] = False   # Disable CSRF for unit tests

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()


@pytest.fixture
def client_csrf():
    """Test client with CSRF enabled, for testing CSRF protection."""
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["WTF_CSRF_SECRET_KEY"] = "csrf-test-secret"

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()


def register_and_login(client, name="Test User", email="test@example.com", password="password123"):
    """Helper: register a user and log them in, return the user."""
    client.post("/register", data={
        "name": name,
        "email": email,
        "password": password,
        "goal": "Get fit",
        "location": "Perth, WA",
    }, follow_redirects=True)

    with app.app_context():
        return User.query.filter_by(email=email).first()


def login(client, email="test@example.com", password="password123"):
    return client.post("/login", data={
        "email": email,
        "password": password,
    }, follow_redirects=True)


# ---------------------------------------------------------------------------
# 1. Registration tests
# ---------------------------------------------------------------------------

class TestRegistration:

    def test_register_new_user(self, client):
        """Registering with valid details creates a user and redirects to dashboard."""
        response = client.post("/register", data={
            "name": "Alice",
            "email": "alice@example.com",
            "password": "securepass",
        }, follow_redirects=True)

        assert response.status_code == 200
        with app.app_context():
            user = User.query.filter_by(email="alice@example.com").first()
            assert user is not None
            assert user.name == "Alice"

    def test_register_duplicate_email(self, client):
        """Registering with an existing email shows an error."""
        data = {"name": "Bob", "email": "bob@example.com", "password": "pass123"}
        client.post("/register", data=data, follow_redirects=True)
        client.get("/logout")
        # Second attempt with same email — should stay on register page with error
        response = client.post("/register", data=data)
        assert response.status_code == 200
        # Confirm only one user exists with this email
        with app.app_context():
            count = User.query.filter_by(email="bob@example.com").count()
            assert count == 1

    def test_register_missing_fields(self, client):
        """Registering without a required field shows an error."""
        response = client.post("/register", data={
            "name": "",
            "email": "nobody@example.com",
            "password": "pass",
        }, follow_redirects=True)

        assert b"required" in response.data

    def test_password_is_hashed(self, client):
        """Raw password must not be stored in the database."""
        client.post("/register", data={
            "name": "Carol",
            "email": "carol@example.com",
            "password": "plaintext",
        })
        with app.app_context():
            user = User.query.filter_by(email="carol@example.com").first()
            assert user.password_hash != "plaintext"
            assert len(user.password_hash) > 20  # bcrypt/scrypt hash is long


# ---------------------------------------------------------------------------
# 2. Login tests
# ---------------------------------------------------------------------------

class TestLogin:

    def test_login_valid_credentials(self, client):
        """Valid credentials log the user in and redirect to dashboard."""
        register_and_login(client)
        response = client.post("/login", data={
            "email": "test@example.com",
            "password": "password123",
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b"dashboard" in response.data.lower() or b"welcome" in response.data.lower()

    def test_login_wrong_password(self, client):
        """Wrong password shows an error and does not log in."""
        register_and_login(client)
        client.get("/logout")  # ensure clean session
        response = client.post("/login", data={
            "email": "test@example.com",
            "password": "wrongpassword",
        })
        # Should stay on login page (200), not redirect to dashboard
        assert response.status_code == 200
        with client.session_transaction() as sess:
            assert "user_id" not in sess

    def test_login_unknown_email(self, client):
        """Unknown email shows an error."""
        response = client.post("/login", data={
            "email": "ghost@example.com",
            "password": "anything",
        }, follow_redirects=True)

        assert b"Invalid" in response.data

    def test_logout_clears_session(self, client):
        """After logout, accessing a protected page redirects to login."""
        register_and_login(client)
        login(client)
        client.get("/logout", follow_redirects=True)

        response = client.get("/dashboard", follow_redirects=True)
        assert b"Login" in response.data or b"login" in response.data


# ---------------------------------------------------------------------------
# 3. Access control tests
# ---------------------------------------------------------------------------

class TestAccessControl:

    def test_dashboard_requires_login(self, client):
        """Unauthenticated request to /dashboard redirects to login."""
        response = client.get("/dashboard", follow_redirects=True)
        assert b"Login" in response.data or b"login" in response.data

    def test_workouts_requires_login(self, client):
        """Unauthenticated request to /workouts redirects to login."""
        response = client.get("/workouts", follow_redirects=True)
        assert b"Login" in response.data or b"login" in response.data

    def test_progress_requires_login(self, client):
        """Unauthenticated request to /progress redirects to login."""
        response = client.get("/progress", follow_redirects=True)
        assert b"Login" in response.data or b"login" in response.data

    def test_profile_requires_login(self, client):
        """Unauthenticated request to /profile redirects to login."""
        response = client.get("/profile", follow_redirects=True)
        assert b"Login" in response.data or b"login" in response.data


# ---------------------------------------------------------------------------
# 4. Workout CRUD tests
# ---------------------------------------------------------------------------

class TestWorkoutCRUD:

    def _add_workout(self, client, email="test@example.com", **overrides):
        """Helper: insert a workout directly into the DB for the given user."""
        with app.app_context():
            user = User.query.filter_by(email=email).first()
            w = Workout(
                date=overrides.get("date", "2026-05-01"),
                type=overrides.get("type", "Running"),
                duration=overrides.get("duration", 30),
                intensity=overrides.get("intensity", "Medium"),
                notes="Test notes",
                user_id=user.id,
            )
            db.session.add(w)
            db.session.commit()
            return w.id

    def test_workout_appears_on_workouts_page(self, client):
        """A saved workout shows up on the workouts page."""
        register_and_login(client)
        login(client)
        workout_id = self._add_workout(client, type="Cycling")

        response = client.get("/workouts")
        assert b"Cycling" in response.data

    def test_edit_workout(self, client):
        """Editing a workout updates its details."""
        register_and_login(client)
        login(client)
        workout_id = self._add_workout(client)

        client.post(f"/workouts/{workout_id}/edit", data={
            "date": "2026-05-10",
            "type": "Swimming",
            "duration": "45",
            "intensity": "High",
            "notes": "Updated notes",
        }, follow_redirects=True)

        with app.app_context():
            w = db.session.get(Workout, workout_id)
            assert w.type == "Swimming"
            assert w.duration == 45

    def test_edit_workout_invalid_date(self, client):
        """Editing a workout with a bad date shows an error."""
        register_and_login(client)
        login(client)
        workout_id = self._add_workout(client)

        response = client.post(f"/workouts/{workout_id}/edit", data={
            "date": "not-a-date",
            "type": "Running",
            "duration": "30",
            "intensity": "Low",
            "notes": "",
        }, follow_redirects=True)

        assert b"YYYY-MM-DD" in response.data or b"format" in response.data.lower()

    def test_delete_workout(self, client):
        """Deleting a workout removes it from the database."""
        register_and_login(client)
        login(client)
        workout_id = self._add_workout(client)

        client.post(f"/workouts/{workout_id}/delete", follow_redirects=True)

        with app.app_context():
            assert db.session.get(Workout, workout_id) is None

    def test_user_cannot_delete_others_workout(self, client):
        """A user cannot delete a workout that belongs to another user."""
        # Register user A and create a workout for them
        register_and_login(client, name="Alice", email="alice@ex.com", password="pass123")
        login(client, email="alice@ex.com", password="pass123")
        workout_id = self._add_workout(client, email="alice@ex.com")
        client.get("/logout")

        # Register and log in as user B
        client.post("/register", data={
            "name": "Bob", "email": "bob@ex.com", "password": "pass123"
        })
        login(client, email="bob@ex.com", password="pass123")

        # Bob tries to delete Alice's workout
        client.post(f"/workouts/{workout_id}/delete", follow_redirects=True)

        with app.app_context():
            # Workout should still exist (it belongs to Alice)
            assert db.session.get(Workout, workout_id) is not None


# ---------------------------------------------------------------------------
# 5. Streak calculation tests
# ---------------------------------------------------------------------------

class TestStreakCalculation:

    def _make_workouts(self, dates):
        """Return mock Workout-like objects with .date set."""
        class FakeWorkout:
            def __init__(self, d):
                self.date = d
        return [FakeWorkout(d) for d in dates]

    def test_streak_empty(self):
        """No workouts gives a streak of 0."""
        assert calculate_streak([]) == 0

    def test_streak_today_only(self):
        """A single workout today gives a streak of 1."""
        today = date.today().isoformat()
        workouts = self._make_workouts([today])
        assert calculate_streak(workouts) == 1

    def test_streak_consecutive_days(self):
        """Workouts on 3 consecutive days ending today gives streak 3."""
        today = date.today()
        dates = [
            (today - timedelta(days=2)).isoformat(),
            (today - timedelta(days=1)).isoformat(),
            today.isoformat(),
        ]
        assert calculate_streak(self._make_workouts(dates)) == 3

    def test_streak_broken_by_gap(self):
        """A gap in the workout history resets the streak."""
        today = date.today()
        dates = [
            (today - timedelta(days=5)).isoformat(),
            (today - timedelta(days=4)).isoformat(),
            # gap on day -3 and -2
            (today - timedelta(days=1)).isoformat(),
            today.isoformat(),
        ]
        assert calculate_streak(self._make_workouts(dates)) == 2

    def test_streak_yesterday_no_today(self):
        """If the user worked out yesterday but not today, streak still counts."""
        today = date.today()
        dates = [
            (today - timedelta(days=2)).isoformat(),
            (today - timedelta(days=1)).isoformat(),
        ]
        assert calculate_streak(self._make_workouts(dates)) == 2

    def test_streak_future_dates_ignored(self):
        """Future-dated workouts do not inflate the streak."""
        today = date.today()
        dates = [
            today.isoformat(),
            (today + timedelta(days=1)).isoformat(),
        ]
        assert calculate_streak(self._make_workouts(dates)) == 1

    def test_streak_duplicate_dates(self):
        """Multiple workouts on the same day count as one day."""
        today = date.today()
        dates = [today.isoformat(), today.isoformat(), today.isoformat()]
        assert calculate_streak(self._make_workouts(dates)) == 1


# ---------------------------------------------------------------------------
# 6. Progress statistics tests
# ---------------------------------------------------------------------------

class TestProgressStats:

    def test_progress_stats_empty(self, client):
        """A new user with no workouts sees all-zero stats."""
        register_and_login(client)
        login(client)

        response = client.get("/progress")
        assert b"0" in response.data

    def test_progress_stats_calculated(self, client):
        """Progress page shows correct totals after workouts are added."""
        register_and_login(client)
        login(client)

        with app.app_context():
            user = User.query.filter_by(email="test@example.com").first()
            db.session.add_all([
                Workout(date="2026-05-01", type="Running",  duration=30, intensity="Medium", user_id=user.id),
                Workout(date="2026-05-02", type="Cycling",  duration=45, intensity="Low",    user_id=user.id),
            ])
            db.session.commit()

        response = client.get("/progress")
        assert b"75" in response.data   # 30 + 45 total minutes
        assert b"2"  in response.data   # 2 workouts


# ---------------------------------------------------------------------------
# 7. Profile edit tests
# ---------------------------------------------------------------------------

class TestProfileEdit:

    def test_edit_profile_updates_name(self, client):
        """Editing a profile with a new name updates the database."""
        register_and_login(client)
        login(client)

        client.post("/profile/edit", data={
            "name": "Updated Name",
            "goal": "Run a marathon",
            "location": "Sydney",
        }, follow_redirects=True)

        with app.app_context():
            user = User.query.filter_by(email="test@example.com").first()
            assert user.name == "Updated Name"

    def test_edit_profile_empty_name_rejected(self, client):
        """An empty name is rejected on profile edit."""
        register_and_login(client)
        login(client)

        response = client.post("/profile/edit", data={
            "name": "",
            "goal": "Some goal",
            "location": "Perth",
        }, follow_redirects=True)

        assert b"cannot be empty" in response.data or b"Name" in response.data
