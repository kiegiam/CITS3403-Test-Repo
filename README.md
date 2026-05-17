# CITS3403 Project Repo

# FitTrack

## Purpose of the application

FitTrack is a health and fitness tracking web application that helps users log workouts, monitor their progress, and stay motivated through community features such as rankings and shared statistics.

The application is designed to be simple and intuitive for everyday fitness tracking. Users can create an account, log in securely, manage their profile, add and edit workouts, view progress over time, and compare their activity with other users through community leaderboard features. The design focuses on clarity, ease of use, and encouraging consistent exercise habits.

## Design and use

FitTrack uses a client-server architecture built with Flask. The frontend is developed using HTML, CSS, JavaScript, and Bootstrap, while user and workout data are stored in SQLite through SQLAlchemy.

Main features include:
- User registration, login, and logout with secure password hashing
- Password reset via email verification code
- Editable user profiles with avatar upload
- Workout logging and management with live stopwatch timer
- Progress tracking with charts and statistics
- Personalised workout plan recommendations
- Plan-based exercise recommendations
- Community ranking features with privacy controls
- CSRF protection on all forms
- Responsive interface for use across devices

## Group members

| UWA ID | Name | GitHub username |
|-------|------|-----------------|
| 24038858 | Giam Kie Shen | kiegiam |
| 24017328 | Steven Wang | docx1145 |
| 23902662 | Lucas Wu | whxgit665 |
| 23986795 | Tanish Khurana | tanish-khurana |

## Instructions to launch the application

### Recommended Python version

This project is recommended to run with **Python 3.12**.

Using a very new Python version may cause some packages in `requirements.txt` to fail during installation because pre-built wheels may not be available yet.

Check your Python version:

```bash
python --version
```

If you are using Windows and `python` points to `WindowsApps`, install Python from the official Python website and make sure Python is added to PATH.

If needed, disable the Windows App Execution Alias for `python.exe` and `python3.exe`:

```text
Settings → Apps → Advanced app settings → App execution aliases
```

Then turn off:

```text
python.exe
python3.exe
```

### 1. Clone the repository

```bash
git clone https://github.com/kiegiam/CITS3403-Test-Repo.git
cd CITS3403-Test-Repo
```

### 2. Create and activate a virtual environment

#### Windows PowerShell

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks the activation script, run:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\venv\Scripts\Activate.ps1
```

After activation, the terminal should show `(venv)` at the start of the command line.

#### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install the required dependencies

Install dependencies inside the virtual environment:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

### 4. Initialise the database

Set a local secret key before running the app or database setup scripts:

#### Windows PowerShell

```powershell
$env:SECRET_KEY = "replace-this-with-a-local-development-secret"
```

#### macOS / Linux

```bash
export SECRET_KEY="replace-this-with-a-local-development-secret"
```

```bash
python init_db.py
```

### 5. Run the application

```bash
python app.py
```

### 6. Open the application

After running `app.py`, open the following link in your browser:

```text
http://127.0.0.1:5000
```

A demo account is available to explore the app immediately:

- **Email:** demo@fittrack.com
- **Password:** password123

## Troubleshooting setup issues

### Python command does not work on Windows

If `python --version` does not show a real Python version, Python may not be installed correctly or Windows may be using the Microsoft Store placeholder.

Try:

```powershell
where.exe python
```

If it shows a path like:

```text
C:\Users\<username>\AppData\Local\Microsoft\WindowsApps\python.exe
```

install Python 3.12 from the official Python website and make sure **Add python.exe to PATH** is selected during installation.

### Requirements installation fails

If `pip install -r requirements.txt` fails on a new laptop, check the Python version first:

```bash
python --version
```

This project is recommended to run with Python 3.12. Some packages may fail to install on very new Python versions because compatible pre-built wheels may not be available yet.

After changing Python versions, delete the old virtual environment and create a new one:

#### Windows PowerShell

```powershell
deactivate
Remove-Item -Recurse -Force venv
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

#### macOS / Linux

```bash
deactivate
rm -rf venv
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

## How to run the tests

The test suite contains 41 unit tests and 25 Selenium tests.

### Unit tests

Unit tests use an in-memory database and do not require the server to be running.

#### Windows PowerShell

```powershell
.\venv\Scripts\Activate.ps1
python -m pytest tests/test_unit.py -v
```

#### macOS / Linux

```bash
source venv/bin/activate
python -m pytest tests/test_unit.py -v
```

The unit tests cover:
- User registration and login
- Access control (login required routes)
- Workout CRUD (add, edit, delete, ownership protection)
- Streak calculation
- Progress statistics
- Password validation
- Profile editing
- Password reset flow

### Selenium tests

Selenium tests run against a live instance of the application. Open two terminal windows.

#### Terminal 1 — start the server

Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
python app.py
```

macOS / Linux:

```bash
source venv/bin/activate
python app.py
```

#### Terminal 2 — run the Selenium tests

Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
python -m pytest tests/test_selenium.py -v
```

macOS / Linux:

```bash
source venv/bin/activate
python -m pytest tests/test_selenium.py -v
```

The Selenium tests cover:
- Home page content and navigation
- Login and logout flow including JavaScript validation
- User registration flow
- Dashboard stats and links
- Workouts page search and intensity filter
- Progress page statistics
- Profile page content and edit navigation
- Navbar links and unauthenticated access redirects

**Requirements for Selenium tests:**
- Google Chrome must be installed
- ChromeDriver must be installed and on your PATH
  - Mac: `brew install chromedriver`
  - Or download from https://chromedriver.chromium.org
  - ChromeDriver version must match your installed Chrome version

### Run all tests at once

```bash
python -m pytest tests/ -v
```

## Site Walkthrough

### 1. Index page / Landing page

The landing page introduces FitTrack and funnels users into the login and register pages. Users who are already logged in will be redirected away from this page automatically.

### 2. Register page `/register`

The register page allows new users to create an account. Users must provide a name, email address, and a valid password. Passwords must be confirmed and duplicate email addresses are not allowed. After successful registration, users are redirected to the dashboard.

### 3. Login page `/login`

The login page allows existing users to sign in. Client-side JavaScript validates the email and password fields before submission. If the login details are correct, the user is taken to the dashboard. If not, an error message is shown. Users can also request a password reset via email verification code.

### 4. Forgot password page `/forgot-password`

Users can enter their registered email address to receive a 6-digit verification code. After verifying the code, they are prompted to set a new password.

### 5. Dashboard page `/dashboard`

The dashboard is the main landing page after login. It provides a quick overview of the user's fitness activity, including total workouts, total minutes, current streak, and recent training sessions.

### 6. Profile page `/profile`

The profile page displays the user's personal fitness profile, including their name, email, goal, location, member information, and profile picture. If no profile picture is uploaded, the site displays a default initials-based icon.

### 7. Edit profile page `/profile/edit`

The edit profile page allows users to update their personal details, upload or remove a profile picture, and manage community privacy settings. Users can choose whether their profile and fitness progress are visible on the ranking page.

### 8. Plans page `/plans`

The plans page helps users set training goals, view a weekly planning structure, and receive personalised workout plan recommendations. The recommendation system considers the user's goal, fitness level, available training days, session length, equipment access, training preference, and training needs.

### 9. Add workout page `/workouts/add`

The add workout page lets users log a new workout session. Users select muscle groups and exercises, record sets with reps and weights, and track duration using a live stopwatch or manual entry. If a user starts from a selected plan, the page can show recommended exercises while still allowing users to choose any exercise manually.

### 10. My Workouts page `/workouts`

The workouts page shows the user's full workout history. Users can search by type, filter by intensity, and sort by date or duration. Each workout can be edited or deleted.

### 11. Edit workout page `/workouts/<workout_id>/edit`

The edit workout page allows users to update the date, type, duration, intensity, and notes of an existing workout. Future dates are not permitted.

### 12. Progress page `/progress`

The progress page summarises the user's training over time, showing total workouts, total minutes, average duration, current streak, workout type breakdown, and recent history.

### 13. Ranking page `/ranking`

The ranking page shows a community leaderboard of users who have enabled fitness sharing. Users who have disabled sharing appear as private. Rankings are ordered by total workout minutes.

### 14. Logout `/logout`

The logout route clears the user's session and returns them to the home page.
