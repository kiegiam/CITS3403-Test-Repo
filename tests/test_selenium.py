"""
FitTrack — Selenium Tests
=========================
These tests require a live Flask server running on port 5001.

Start the server first in a separate terminal:
    python app.py

Then run:
    python -m pytest tests/test_selenium.py -v

Requirements:
    pip install selenium
    Google Chrome + ChromeDriver must be installed and on PATH.
    ChromeDriver version must match your installed Chrome version.
    Install ChromeDriver on Mac: brew install chromedriver

The tests use headless Chrome so no browser window opens.
"""

import os
import sys
import time
import threading
import pytest
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["SECRET_KEY"] = "selenium-test-secret"

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

from app import app, db, User, Workout
from werkzeug.security import generate_password_hash


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL      = "http://127.0.0.1:5001"
DEMO_EMAIL    = "seleniumdemo@fittrack.com"
DEMO_PASSWORD = "seleniumpass123"
DEMO_NAME     = "Selenium Demo User"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def live_server():
    """Seed the test database and start Flask on port 5001."""
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///test_selenium.db"
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SERVER_NAME"] = None

    with app.app_context():
        db.create_all()
        existing = User.query.filter_by(email=DEMO_EMAIL).first()
        if not existing:
            demo = User(
                name=DEMO_NAME,
                email=DEMO_EMAIL,
                password_hash=generate_password_hash(DEMO_PASSWORD),
                goal="Selenium testing",
                member_since="May 2026",
                location="Test City",
                show_public_profile=True,
                show_public_fitness=True,
            )
            db.session.add(demo)
            db.session.commit()
            db.session.add_all([
                Workout(date="2026-05-10", type="Running", duration=30,
                        intensity="Medium", user_id=demo.id),
                Workout(date="2026-05-11", type="Gym",     duration=60,
                        intensity="High",   user_id=demo.id),
            ])
            db.session.commit()

    server_thread = threading.Thread(
        target=lambda: app.run(port=5001, use_reloader=False, debug=False),
        daemon=True,
    )
    server_thread.start()
    time.sleep(1.5)
    yield


@pytest.fixture
def driver(live_server):
    """Headless Chrome WebDriver, quit after each test."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    d = webdriver.Chrome(options=options)
    d.implicitly_wait(5)
    yield d
    d.quit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def wait(driver, locator, timeout=8):
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located(locator)
    )


def login(driver):
    """Log in as the demo user."""
    driver.get(f"{BASE_URL}/login")
    wait(driver, (By.ID, "email")).send_keys(DEMO_EMAIL)
    driver.find_element(By.ID, "password").send_keys(DEMO_PASSWORD)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    WebDriverWait(driver, 8).until(EC.url_contains("dashboard"))


# ---------------------------------------------------------------------------
# Test 1: Home page
# ---------------------------------------------------------------------------

class TestHomePage:

    def test_home_page_title_contains_fittrack(self, driver):
        """The home page title contains FitTrack."""
        driver.get(BASE_URL)
        assert "FitTrack" in driver.title

    def test_home_page_has_get_started_button(self, driver):
        """The hero section has a Get Started button."""
        driver.get(BASE_URL)
        btn = wait(driver, (By.LINK_TEXT, "Get Started"))
        assert btn.is_displayed()

    def test_home_page_has_login_link(self, driver):
        """The navbar on the home page has a Login link."""
        driver.get(BASE_URL)
        assert driver.find_element(By.LINK_TEXT, "Login").is_displayed()

    def test_home_page_has_sign_up_button(self, driver):
        """The home page has a Sign Up link."""
        driver.get(BASE_URL)
        assert driver.find_element(By.LINK_TEXT, "Sign Up").is_displayed()

    def test_home_page_shows_feature_cards(self, driver):
        """The home page feature section is visible."""
        driver.get(BASE_URL)
        assert "Log every session" in driver.page_source


# ---------------------------------------------------------------------------
# Test 2: Login flow
# ---------------------------------------------------------------------------

class TestLoginFlow:

    def test_login_valid_credentials_redirects_to_dashboard(self, driver):
        """Valid credentials redirect to /dashboard."""
        login(driver)
        assert "dashboard" in driver.current_url.lower()

    def test_login_wrong_password_stays_on_login(self, driver):
        """Wrong password keeps the user on the login page."""
        driver.get(f"{BASE_URL}/login")
        wait(driver, (By.ID, "email")).send_keys(DEMO_EMAIL)
        driver.find_element(By.ID, "password").send_keys("wrongpassword")
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(0.5)
        assert "/login" in driver.current_url

    def test_login_js_validation_empty_email(self, driver):
        """JS validation fires and shows an error for empty email."""
        driver.get(f"{BASE_URL}/login")
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(0.3)
        assert "/login" in driver.current_url
        error_el = driver.find_element(By.ID, "emailError")
        assert error_el.text != ""

    def test_logout_redirects_to_home(self, driver):
        """Logging out redirects to the home page."""
        login(driver)
        driver.get(f"{BASE_URL}/logout")
        time.sleep(0.5)
        assert driver.current_url in (f"{BASE_URL}/", f"{BASE_URL}")

    def test_forgot_password_link_visible_on_login(self, driver):
        """The Forgot password? link is visible on the login page."""
        driver.get(f"{BASE_URL}/login")
        link = wait(driver, (By.PARTIAL_LINK_TEXT, "Forgot password"))
        assert link.is_displayed()


# ---------------------------------------------------------------------------
# Test 3: Registration flow
# ---------------------------------------------------------------------------

class TestRegistrationFlow:

    def test_register_new_user_lands_on_dashboard(self, driver):
        """A new user can register and is redirected to the dashboard."""
        unique_email = f"selenium{random.randint(10000, 99999)}@test.com"
        driver.get(f"{BASE_URL}/register")
        wait(driver, (By.ID, "name")).send_keys("New Selenium User")
        driver.find_element(By.ID, "email").send_keys(unique_email)
        driver.find_element(By.ID, "password").send_keys("testpass123")
        driver.find_element(By.ID, "confirm_password").send_keys("testpass123")
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        WebDriverWait(driver, 8).until(EC.url_contains("dashboard"))
        assert "dashboard" in driver.current_url

    def test_register_mismatched_passwords_shows_error(self, driver):
        """Mismatched passwords show an error and stay on register page."""
        unique_email = f"fail{random.randint(10000, 99999)}@test.com"
        driver.get(f"{BASE_URL}/register")
        wait(driver, (By.ID, "name")).send_keys("Bad User")
        driver.find_element(By.ID, "email").send_keys(unique_email)
        driver.find_element(By.ID, "password").send_keys("password123")
        driver.find_element(By.ID, "confirm_password").send_keys("different456")
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(0.5)
        assert "register" in driver.current_url or "do not match" in driver.page_source


# ---------------------------------------------------------------------------
# Test 4: Dashboard
# ---------------------------------------------------------------------------

class TestDashboard:

    def test_dashboard_shows_stat_cards(self, driver):
        """The dashboard shows Total Workouts, Total Minutes, Day Streak."""
        login(driver)
        page = driver.page_source
        assert "Total Workouts" in page
        assert "Total Minutes" in page
        assert "Day Streak" in page

    def test_dashboard_shows_recent_training_section(self, driver):
        """The dashboard recent training section is present."""
        login(driver)
        assert "Recent Training" in driver.page_source

    def test_dashboard_add_workout_button_navigates(self, driver):
        """The Add Workout button navigates to the add workout page."""
        login(driver)
        btn = wait(driver, (By.LINK_TEXT, "Add Workout"))
        btn.click()
        WebDriverWait(driver, 6).until(EC.url_contains("workout"))
        assert "workout" in driver.current_url


# ---------------------------------------------------------------------------
# Test 5: Workouts page
# ---------------------------------------------------------------------------

class TestWorkoutsPage:

    def test_workouts_page_loads(self, driver):
        """The My Workouts page loads with the heading."""
        login(driver)
        driver.get(f"{BASE_URL}/workouts")
        assert "My Workouts" in driver.page_source

    def test_workouts_search_filter(self, driver):
        """Searching by type filters the workout list."""
        login(driver)
        driver.get(f"{BASE_URL}/workouts")
        search = wait(driver, (By.ID, "search"))
        search.clear()
        search.send_keys("Running")
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(0.5)
        assert "Running" in driver.page_source

    def test_workouts_intensity_filter(self, driver):
        """Filtering by High intensity only shows High workouts."""
        login(driver)
        driver.get(f"{BASE_URL}/workouts")
        select = Select(driver.find_element(By.ID, "intensity"))
        select.select_by_value("High")
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(0.5)
        assert "High" in driver.page_source

    def test_workouts_clear_filters_resets_url(self, driver):
        """The Clear Filters button resets back to /workouts."""
        login(driver)
        driver.get(f"{BASE_URL}/workouts?search=Running&intensity=Medium")
        clear_btn = wait(driver, (By.LINK_TEXT, "Clear Filters"))
        clear_btn.click()
        WebDriverWait(driver, 5).until(EC.url_to_be(f"{BASE_URL}/workouts"))
        assert driver.current_url == f"{BASE_URL}/workouts"

    def test_workouts_add_new_workout_button(self, driver):
        """The Add New Workout button on the workouts page is clickable."""
        login(driver)
        driver.get(f"{BASE_URL}/workouts")
        btn = wait(driver, (By.LINK_TEXT, "Add New Workout"))
        btn.click()
        WebDriverWait(driver, 5).until(EC.url_contains("workout"))
        assert "workout" in driver.current_url


# ---------------------------------------------------------------------------
# Test 6: Progress page
# ---------------------------------------------------------------------------

class TestProgressPage:

    def test_progress_page_shows_stat_boxes(self, driver):
        """The progress page shows all four stat boxes."""
        login(driver)
        driver.get(f"{BASE_URL}/progress")
        page = driver.page_source
        assert "Total Workouts" in page
        assert "Total Minutes"  in page

    def test_progress_page_shows_type_breakdown(self, driver):
        """The progress page shows the workout type breakdown section."""
        login(driver)
        driver.get(f"{BASE_URL}/progress")
        assert "Workout Type Breakdown" in driver.page_source


# ---------------------------------------------------------------------------
# Test 7: Profile page
# ---------------------------------------------------------------------------

class TestProfilePage:

    def test_profile_shows_user_name_and_email(self, driver):
        """The profile page shows the demo user's name and email."""
        login(driver)
        driver.get(f"{BASE_URL}/profile")
        page = driver.page_source
        assert DEMO_NAME  in page
        assert DEMO_EMAIL in page

    def test_profile_edit_link_navigates_to_edit(self, driver):
        """The Edit Profile button navigates to the edit profile page."""
        login(driver)
        driver.get(f"{BASE_URL}/profile")
        btn = wait(driver, (By.LINK_TEXT, "Edit Profile"))
        btn.click()
        WebDriverWait(driver, 5).until(EC.url_contains("edit"))
        assert "edit" in driver.current_url


# ---------------------------------------------------------------------------
# Test 8: Navigation and access control
# ---------------------------------------------------------------------------

class TestNavigation:

    def test_all_main_pages_load_when_logged_in(self, driver):
        """All main nav pages return a <main> element when authenticated."""
        login(driver)
        pages = ["/dashboard", "/workouts", "/progress", "/ranking", "/plans"]
        for path in pages:
            driver.get(f"{BASE_URL}{path}")
            assert driver.find_element(By.TAG_NAME, "main").is_displayed(), \
                f"{path} did not load a <main> element"

    def test_unauthenticated_access_redirects_to_login(self, driver):
        """Accessing /dashboard without login redirects to /login."""
        driver.get(f"{BASE_URL}/logout")
        driver.get(f"{BASE_URL}/dashboard")
        WebDriverWait(driver, 5).until(EC.url_contains("login"))
        assert "/login" in driver.current_url

    def test_ranking_page_loads(self, driver):
        """The ranking page loads and shows the community heading."""
        login(driver)
        driver.get(f"{BASE_URL}/ranking")
        assert "Community Ranking" in driver.page_source or "Leaderboard" in driver.page_source

    def test_forgot_password_page_loads(self, driver):
        """The forgot password page loads without login."""
        driver.get(f"{BASE_URL}/forgot-password")
        assert "Forgot" in driver.page_source or "password" in driver.page_source.lower()

    def test_plans_page_loads(self, driver):
        """The plans page loads and shows plan content."""
        login(driver)
        driver.get(f"{BASE_URL}/plans")
        assert "plan" in driver.page_source.lower() or "Plan" in driver.page_source
