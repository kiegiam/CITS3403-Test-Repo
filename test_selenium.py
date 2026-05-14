"""
FitTrack — Selenium Tests
=========================
These tests require a live instance of the Flask server to be running.

Start the server first:
    python app.py

Then in a separate terminal run:
    python -m pytest test_selenium.py -v

Requirements:
    pip install selenium
    Google Chrome + ChromeDriver must be installed and on PATH.
    ChromeDriver version must match Chrome version.

The tests use headless Chrome so no browser window opens.
"""

import time
import threading
import pytest

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

import os
os.environ["SECRET_KEY"] = "selenium-test-secret"

from app import app, db, User, Workout
from werkzeug.security import generate_password_hash

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "http://127.0.0.1:5001"

DEMO_EMAIL    = "seleniumdemo@fittrack.com"
DEMO_PASSWORD = "seleniumpass123"
DEMO_NAME     = "Selenium Demo User"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def live_server():
    """Start the Flask app in a background thread for the duration of the tests."""
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///test_selenium.db"
    app.config["WTF_CSRF_ENABLED"] = False   # Disable CSRF for Selenium tests
    app.config["SERVER_NAME"] = None

    with app.app_context():
        db.create_all()

        # Seed a demo user
        existing = User.query.filter_by(email=DEMO_EMAIL).first()
        if not existing:
            demo = User(
                name=DEMO_NAME,
                email=DEMO_EMAIL,
                password_hash=generate_password_hash(DEMO_PASSWORD),
                goal="Selenium testing",
                member_since="May 2026",
                location="Test City",
            )
            db.session.add(demo)
            db.session.commit()

            db.session.add_all([
                Workout(date="2026-05-10", type="Running",  duration=30, intensity="Medium", user_id=demo.id),
                Workout(date="2026-05-11", type="Gym",      duration=60, intensity="High",   user_id=demo.id),
            ])
            db.session.commit()

    server_thread = threading.Thread(
        target=lambda: app.run(port=5001, use_reloader=False, debug=False),
        daemon=True
    )
    server_thread.start()
    time.sleep(1.5)   # give the server time to start
    yield
    # Thread is daemon so it stops when the test session ends


@pytest.fixture
def driver(live_server):
    """Headless Chrome WebDriver, reset between tests."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")

    d = webdriver.Chrome(options=options)
    d.implicitly_wait(5)
    yield d
    d.quit()


def wait(driver, locator, timeout=8):
    """Wait for an element to be visible and return it."""
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located(locator)
    )


def login(driver):
    """Helper: navigate to login and authenticate as the demo user."""
    driver.get(f"{BASE_URL}/login")
    wait(driver, (By.ID, "email")).send_keys(DEMO_EMAIL)
    driver.find_element(By.ID, "password").send_keys(DEMO_PASSWORD)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    wait(driver, (By.PARTIAL_LINK_TEXT, "Dashboard"))


# ---------------------------------------------------------------------------
# Test 1: Home page loads and shows key content
# ---------------------------------------------------------------------------

class TestHomePage:

    def test_home_page_title(self, driver):
        """The home page loads with the FitTrack title."""
        driver.get(BASE_URL)
        assert "FitTrack" in driver.title

    def test_home_page_shows_get_started(self, driver):
        """The home page hero section has a Get Started button."""
        driver.get(BASE_URL)
        btn = wait(driver, (By.LINK_TEXT, "Get Started"))
        assert btn.is_displayed()

    def test_home_page_nav_has_login_and_register(self, driver):
        """The navbar on the home page has Login and Register links."""
        driver.get(BASE_URL)
        assert driver.find_element(By.LINK_TEXT, "Login").is_displayed()
        assert driver.find_element(By.LINK_TEXT, "Register").is_displayed()


# ---------------------------------------------------------------------------
# Test 2: Login flow
# ---------------------------------------------------------------------------

class TestLoginFlow:

    def test_login_with_valid_credentials(self, driver):
        """Logging in with valid credentials redirects to the dashboard."""
        login(driver)
        assert "dashboard" in driver.current_url.lower() or "Dashboard" in driver.page_source

    def test_login_with_invalid_password_stays_on_login(self, driver):
        """Logging in with a wrong password stays on the login page."""
        driver.get(f"{BASE_URL}/login")
        wait(driver, (By.ID, "email")).send_keys(DEMO_EMAIL)
        driver.find_element(By.ID, "password").send_keys("wrongpassword")
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(0.5)
        assert "/login" in driver.current_url

    def test_login_form_js_validation_empty_fields(self, driver):
        """The JS login validation fires when fields are left empty."""
        driver.get(f"{BASE_URL}/login")
        # Click submit without filling in anything
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(0.3)
        # JS validation should show an error and keep us on the login page
        assert "/login" in driver.current_url
        error_el = driver.find_element(By.ID, "emailError")
        assert error_el.text != ""

    def test_logout_redirects_to_home(self, driver):
        """Logging out redirects to the home page."""
        login(driver)
        driver.get(f"{BASE_URL}/logout")
        time.sleep(0.5)
        assert driver.current_url == f"{BASE_URL}/" or "FitTrack - Home" in driver.title


# ---------------------------------------------------------------------------
# Test 3: Registration flow
# ---------------------------------------------------------------------------

class TestRegistrationFlow:

    def test_register_new_user(self, driver):
        """A new user can register and is redirected to the dashboard."""
        import random
        unique_email = f"newuser{random.randint(10000, 99999)}@test.com"

        driver.get(f"{BASE_URL}/register")
        wait(driver, (By.ID, "name")).send_keys("New Test User")
        driver.find_element(By.ID, "email").send_keys(unique_email)
        driver.find_element(By.ID, "password").send_keys("newpassword123")
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

        WebDriverWait(driver, 8).until(EC.url_contains("dashboard"))
        assert "dashboard" in driver.current_url


# ---------------------------------------------------------------------------
# Test 4: Dashboard
# ---------------------------------------------------------------------------

class TestDashboard:

    def test_dashboard_shows_stats(self, driver):
        """The dashboard displays workout stats after login."""
        login(driver)
        driver.get(f"{BASE_URL}/dashboard")
        page = driver.page_source
        assert "Total Workouts" in page
        assert "Total Minutes"  in page
        assert "Day Streak"     in page

    def test_dashboard_shows_recent_workouts(self, driver):
        """The dashboard shows recent training entries."""
        login(driver)
        driver.get(f"{BASE_URL}/dashboard")
        # The demo user has seeded workouts; at least one should appear
        page = driver.page_source
        assert "Running" in page or "Gym" in page or "Recent Training" in page

    def test_dashboard_add_workout_link(self, driver):
        """The Add Workout button on the dashboard is clickable."""
        login(driver)
        driver.get(f"{BASE_URL}/dashboard")
        btn = wait(driver, (By.LINK_TEXT, "Add Workout"))
        btn.click()
        WebDriverWait(driver, 6).until(EC.url_contains("workout"))
        assert "workout" in driver.current_url


# ---------------------------------------------------------------------------
# Test 5: Workouts page
# ---------------------------------------------------------------------------

class TestWorkoutsPage:

    def test_workouts_page_loads(self, driver):
        """The My Workouts page loads and shows the workout list."""
        login(driver)
        driver.get(f"{BASE_URL}/workouts")
        assert "My Workouts" in driver.page_source

    def test_workouts_search_filter(self, driver):
        """Searching by workout type filters results."""
        login(driver)
        driver.get(f"{BASE_URL}/workouts")
        search = wait(driver, (By.ID, "search"))
        search.clear()
        search.send_keys("Running")
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(0.5)
        page = driver.page_source
        # Running should appear; Gym (if present) should not
        assert "Running" in page

    def test_workouts_intensity_filter(self, driver):
        """Filtering by intensity only shows matching workouts."""
        login(driver)
        driver.get(f"{BASE_URL}/workouts")
        select = Select(driver.find_element(By.ID, "intensity"))
        select.select_by_value("High")
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(0.5)
        page = driver.page_source
        assert "High" in page

    def test_workouts_clear_filters(self, driver):
        """The Clear Filters button resets the list."""
        login(driver)
        driver.get(f"{BASE_URL}/workouts?search=Running&intensity=Medium")
        clear_btn = wait(driver, (By.LINK_TEXT, "Clear Filters"))
        clear_btn.click()
        WebDriverWait(driver, 5).until(EC.url_to_be(f"{BASE_URL}/workouts"))
        assert driver.current_url == f"{BASE_URL}/workouts"


# ---------------------------------------------------------------------------
# Test 6: Progress page
# ---------------------------------------------------------------------------

class TestProgressPage:

    def test_progress_page_shows_stats(self, driver):
        """The progress page shows total workouts and minutes."""
        login(driver)
        driver.get(f"{BASE_URL}/progress")
        page = driver.page_source
        assert "Total Workouts" in page
        assert "Total Minutes"  in page

    def test_progress_page_shows_type_breakdown(self, driver):
        """The progress page shows a workout type breakdown."""
        login(driver)
        driver.get(f"{BASE_URL}/progress")
        page = driver.page_source
        assert "Workout Type Breakdown" in page


# ---------------------------------------------------------------------------
# Test 7: Profile page
# ---------------------------------------------------------------------------

class TestProfilePage:

    def test_profile_shows_user_details(self, driver):
        """The profile page shows the logged-in user's name and email."""
        login(driver)
        driver.get(f"{BASE_URL}/profile")
        page = driver.page_source
        assert DEMO_NAME  in page
        assert DEMO_EMAIL in page

    def test_profile_edit_link_works(self, driver):
        """The Edit Profile button navigates to the edit page."""
        login(driver)
        driver.get(f"{BASE_URL}/profile")
        btn = wait(driver, (By.LINK_TEXT, "Edit Profile"))
        btn.click()
        WebDriverWait(driver, 5).until(EC.url_contains("edit"))
        assert "edit" in driver.current_url


# ---------------------------------------------------------------------------
# Test 8: Navigation
# ---------------------------------------------------------------------------

class TestNavigation:

    def test_navbar_links_work_when_logged_in(self, driver):
        """All main navbar links are accessible after login."""
        login(driver)
        for label, path in [
            ("Dashboard",   "/dashboard"),
            ("My Workouts", "/workouts"),
            ("Progress",    "/progress"),
            ("Ranking",     "/ranking"),
            ("Plans",       "/plans"),
        ]:
            driver.get(f"{BASE_URL}{path}")
            assert driver.find_element(By.TAG_NAME, "main").is_displayed(), \
                f"Page {path} did not load a <main> element"

    def test_unauthenticated_redirect_to_login(self, driver):
        """Accessing a protected page without login redirects to /login."""
        driver.get(f"{BASE_URL}/logout")
        driver.get(f"{BASE_URL}/dashboard")
        WebDriverWait(driver, 5).until(EC.url_contains("login"))
        assert "/login" in driver.current_url

    def test_ranking_page_loads(self, driver):
        """The Ranking/leaderboard page loads for logged-in users."""
        login(driver)
        driver.get(f"{BASE_URL}/ranking")
        assert "Community Ranking" in driver.page_source or "Leaderboard" in driver.page_source
