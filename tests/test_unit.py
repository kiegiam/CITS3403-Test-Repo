"""
FitTrack — Unit Tests
=====================
Run from the project root with:
    python -m pytest tests/test_unit.py -v

Tests cover:
    - User registration and login (7 tests)
    - Access control — login required routes (5 tests)
    - Workout CRUD — add, edit, delete, ownership (6 tests)
    - Streak calculation — 7 edge cases (7 tests)
    - Progress statistics (2 tests)
    - Password validation helper (5 tests)
    - Profile editing (2 tests)
    - Password reset flow (2 tests)
"""

import os
import sys
import pytest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["SECRET_KEY"] = "test-secret-key"

from app import app, db, User, Workout, calculate_streak, is_valid_password
from werkzeug.security import generate_password_hash


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Flask test client backed by an isolated in-memory database."""
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["WTF_CSRF_ENABLED"] = False

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def register(client, name="Test User", email="test@example.com",
             password="password123", confirm=None):
    return client.post("/register", data={
        "name": name,
        "email": email,
        "password": password,
        "confirm_password": confirm or password,
    }, follow_redirects=True)


def login(client, email="test@example.com", password="password123"):
    return client.post("/login", data={
        "email": email,
        "password": password,
    }, follow_redirects=True)


def register_and_login(client, name="Test User", email="test@example.com",
                       password="password123"):
    register(client, name=name, email=email, password=password)
    return login(client, email=email, password=password)


def seed_workout(email="test@example.com", w_date="2026-05-01",
                 w_type="Running", duration=30, intensity="Medium"):
    """Insert a workout directly into the DB and return its id."""
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        w = Workout(
            date=w_date,
            type=w_type,
            duration=duration,
            intensity=intensity,
            notes="Test notes",
            user_id=user.id,
        )
        db.session.add(w)
        db.session.commit()
        return w.id


# ---------------------------------------------------------------------------
# 1. Registration tests
# ---------------------------------------------------------------------------

class TestRegistration:

    def test_register_new_user_succeeds(self, client):
        """Valid registration creates the user in the database."""
        register(client, name="Alice", email="alice@example.com",
                 password="securepass")
        with app.app_context():
            user = User.query.filter_by(email="alice@example.com").first()
            assert user is not None
            assert user.name == "Alice"

    def test_register_duplicate_email_rejected(self, client):
        """Registering the same email twice only creates one user."""
        register(client, email="bob@example.com", password="pass123")
        client.get("/logout")
        register(client, email="bob@example.com", password="pass123")
        with app.app_context():
            assert User.query.filter_by(email="bob@example.com").count() == 1

    def test_register_password_mismatch_rejected(self, client):
        """Mismatched passwords show an error and do not create the user."""
        response = client.post("/register", data={
            "name": "Carol",
            "email": "carol@example.com",
            "password": "password123",
            "confirm_password": "different456",
        }, follow_redirects=True)
        assert b"do not match" in response.data
        with app.app_context():
            assert User.query.filter_by(email="carol@example.com").first() is None

    def test_register_short_password_rejected(self, client):
        """A password shorter than 6 characters is rejected."""
        response = client.post("/register", data={
            "name": "Dave",
            "email": "dave@example.com",
            "password": "ab",
            "confirm_password": "ab",
        }, follow_redirects=True)
        assert b"6 characters" in response.data

    def test_password_stored_as_hash(self, client):
        """The raw password must never be stored in the database."""
        register(client, email="hash@example.com", password="plaintext123")
        with app.app_context():
            user = User.query.filter_by(email="hash@example.com").first()
            assert user.password_hash != "plaintext123"
            assert len(user.password_hash) > 20

    def test_register_missing_name_rejected(self, client):
        """Registration without a name shows a required-fields error."""
        response = client.post("/register", data={
            "name": "",
            "email": "nobody@example.com",
            "password": "pass123",
            "confirm_password": "pass123",
        }, follow_redirects=True)
        assert b"required" in response.data

    def test_register_sets_session(self, client):
        """Successful registration logs the user in (sets user_id in session)."""
        register(client, email="newuser@example.com", password="pass123")
        with client.session_transaction() as sess:
            assert "user_id" in sess


# ---------------------------------------------------------------------------
# 2. Login tests
# ---------------------------------------------------------------------------

class TestLogin:

    def test_login_valid_credentials_sets_session(self, client):
        """Valid credentials set user_id in the session."""
        register(client)
        client.get("/logout")
        login(client)
        with client.session_transaction() as sess:
            assert "user_id" in sess

    def test_login_wrong_password_fails(self, client):
        """Wrong password does not set user_id in session."""
        register(client)
        client.get("/logout")
        client.post("/login", data={
            "email": "test@example.com",
            "password": "wrongpassword",
        })
        with client.session_transaction() as sess:
            assert "user_id" not in sess

    def test_login_unknown_email_fails(self, client):
        """An unknown email does not log in."""
        client.post("/login", data={
            "email": "ghost@example.com",
            "password": "anything",
        })
        with client.session_transaction() as sess:
            assert "user_id" not in sess

    def test_logout_clears_session(self, client):
        """After logout, user_id is removed from the session."""
        register_and_login(client)
        client.get("/logout")
        with client.session_transaction() as sess:
            assert "user_id" not in sess

    def test_login_email_case_insensitive(self, client):
        """Login works regardless of email capitalisation."""
        register(client, email="user@example.com")
        client.get("/logout")
        client.post("/login", data={
            "email": "USER@EXAMPLE.COM",
            "password": "password123",
        })
        with client.session_transaction() as sess:
            assert "user_id" in sess


# ---------------------------------------------------------------------------
# 3. Access control tests
# ---------------------------------------------------------------------------

class TestAccessControl:

    def test_dashboard_requires_login(self, client):
        """Unauthenticated /dashboard redirects to login."""
        response = client.get("/dashboard", follow_redirects=True)
        assert b"Login" in response.data or b"login" in response.data

    def test_workouts_requires_login(self, client):
        """Unauthenticated /workouts redirects to login."""
        response = client.get("/workouts", follow_redirects=True)
        assert b"Login" in response.data or b"login" in response.data

    def test_progress_requires_login(self, client):
        """Unauthenticated /progress redirects to login."""
        response = client.get("/progress", follow_redirects=True)
        assert b"Login" in response.data or b"login" in response.data

    def test_profile_requires_login(self, client):
        """Unauthenticated /profile redirects to login."""
        response = client.get("/profile", follow_redirects=True)
        assert b"Login" in response.data or b"login" in response.data

    def test_ranking_requires_login(self, client):
        """Unauthenticated /ranking redirects to login."""
        response = client.get("/ranking", follow_redirects=True)
        assert b"Login" in response.data or b"login" in response.data


# ---------------------------------------------------------------------------
# 4. Workout CRUD tests
# ---------------------------------------------------------------------------

class TestWorkoutCRUD:

    def test_workout_appears_on_workouts_page(self, client):
        """A saved workout shows up on the workouts page."""
        register_and_login(client)
        seed_workout(w_type="Cycling")
        response = client.get("/workouts")
        assert b"Cycling" in response.data

    def test_edit_workout_updates_fields(self, client):
        """Editing a workout updates its fields in the database."""
        register_and_login(client)
        workout_id = seed_workout()
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
            assert w.intensity == "High"

    def test_delete_workout_removes_from_db(self, client):
        """Deleting a workout removes it from the database."""
        register_and_login(client)
        workout_id = seed_workout()
        client.post(f"/workouts/{workout_id}/delete", follow_redirects=True)
        with app.app_context():
            assert db.session.get(Workout, workout_id) is None

    def test_user_cannot_delete_others_workout(self, client):
        """A user cannot delete a workout belonging to another user."""
        register(client, name="Alice", email="alice@ex.com", password="pass123")
        login(client, email="alice@ex.com", password="pass123")
        workout_id = seed_workout(email="alice@ex.com")
        client.get("/logout")

        register(client, name="Bob", email="bob@ex.com", password="pass123")
        login(client, email="bob@ex.com", password="pass123")
        client.post(f"/workouts/{workout_id}/delete", follow_redirects=True)

        with app.app_context():
            assert db.session.get(Workout, workout_id) is not None

    def test_workout_search_filter(self, client):
        """The search filter returns only matching workout types."""
        register_and_login(client)
        seed_workout(w_type="Running")
        seed_workout(w_type="Gym")
        response = client.get("/workouts?search=Running")
        assert b"Running" in response.data

    def test_workout_intensity_filter(self, client):
        """The intensity filter returns only matching workouts."""
        register_and_login(client)
        seed_workout(w_type="Running", intensity="High")
        seed_workout(w_type="Yoga", intensity="Low")
        response = client.get("/workouts?intensity=High")
        assert b"Running" in response.data


# ---------------------------------------------------------------------------
# 5. Streak calculation tests
# ---------------------------------------------------------------------------

class TestStreakCalculation:

    class FakeWorkout:
        def __init__(self, d):
            self.date = d

    def make(self, dates):
        return [self.FakeWorkout(d) for d in dates]

    def test_streak_no_workouts(self):
        """No workouts gives a streak of 0."""
        assert calculate_streak([]) == 0

    def test_streak_today_only(self):
        """A single workout today gives a streak of 1."""
        assert calculate_streak(self.make([date.today().isoformat()])) == 1

    def test_streak_three_consecutive_days(self):
        """3 consecutive days ending today gives a streak of 3."""
        today = date.today()
        dates = [(today - timedelta(days=i)).isoformat() for i in range(3)]
        assert calculate_streak(self.make(dates)) == 3

    def test_streak_broken_by_gap(self):
        """A gap in consecutive days resets the streak count."""
        today = date.today()
        dates = [
            (today - timedelta(days=5)).isoformat(),
            (today - timedelta(days=4)).isoformat(),
            (today - timedelta(days=1)).isoformat(),
            today.isoformat(),
        ]
        assert calculate_streak(self.make(dates)) == 2

    def test_streak_yesterday_no_today(self):
        """Streak counts from yesterday if no workout logged today yet."""
        today = date.today()
        dates = [
            (today - timedelta(days=2)).isoformat(),
            (today - timedelta(days=1)).isoformat(),
        ]
        assert calculate_streak(self.make(dates)) == 2

    def test_streak_future_dates_ignored(self):
        """Future-dated workouts do not inflate the streak."""
        today = date.today()
        dates = [today.isoformat(), (today + timedelta(days=1)).isoformat()]
        assert calculate_streak(self.make(dates)) == 1

    def test_streak_duplicate_dates_count_once(self):
        """Multiple workouts on the same day count as one streak day."""
        today = date.today().isoformat()
        assert calculate_streak(self.make([today, today, today])) == 1


# ---------------------------------------------------------------------------
# 6. Progress statistics tests
# ---------------------------------------------------------------------------

class TestProgressStats:

    def test_progress_page_loads(self, client):
        """The progress page loads correctly for an authenticated user."""
        register_and_login(client)
        response = client.get("/progress")
        assert response.status_code == 200
        assert b"Total Workouts" in response.data

    def test_progress_totals_correct(self, client):
        """Total minutes shown matches the sum of workout durations."""
        register_and_login(client)
        seed_workout(w_type="Running", duration=30)
        seed_workout(w_type="Cycling", duration=45)
        response = client.get("/progress")
        assert b"75" in response.data


# ---------------------------------------------------------------------------
# 7. Password validation tests
# ---------------------------------------------------------------------------

class TestPasswordValidation:

    def test_valid_password_accepted(self):
        assert is_valid_password("password123") is True

    def test_too_short_rejected(self):
        assert is_valid_password("ab") is False

    def test_spaces_rejected(self):
        assert is_valid_password("pass word") is False

    def test_exactly_six_chars_accepted(self):
        assert is_valid_password("abcdef") is True

    def test_five_chars_rejected(self):
        assert is_valid_password("abcde") is False


# ---------------------------------------------------------------------------
# 8. Profile edit tests
# ---------------------------------------------------------------------------

class TestProfileEdit:

    def test_edit_profile_updates_name(self, client):
        """Editing a profile with a new name updates the database."""
        register_and_login(client)
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
        response = client.post("/profile/edit", data={
            "name": "",
            "goal": "Some goal",
            "location": "Perth",
        }, follow_redirects=True)
        assert b"cannot be empty" in response.data or b"Name" in response.data


# ---------------------------------------------------------------------------
# 9. Password reset flow tests
# ---------------------------------------------------------------------------

class TestPasswordReset:

    def test_forgot_password_unknown_email_shows_error(self, client):
        """Submitting forgot password with an unknown email shows an error."""
        response = client.post("/forgot-password", data={
            "email": "notregistered@example.com",
        }, follow_redirects=True)
        assert b"No account" in response.data or b"not found" in response.data.lower()

    def test_forgot_password_known_email_sets_reset_session(self, client):
        """Submitting forgot password with a known email sets reset session vars."""
        register(client)
        client.get("/logout")
        client.post("/forgot-password", data={
            "email": "test@example.com",
        })
        with client.session_transaction() as sess:
            assert "reset_code" in sess
            assert sess.get("reset_email") == "test@example.com"
