# CITS3403 Project Repo

# FitTrack

## Purpose of the application

FitTrack is a health and fitness tracking web application that helps users log workouts, monitor their progress, and stay motivated through community features such as rankings and shared statistics.

The application is designed to be simple and intuitive for everyday fitness tracking. Users can create an account, log in securely, manage their profile, add and edit workouts, view progress over time, and compare their activity with other users through community leaderboard features. The design focuses on clarity, ease of use, and encouraging consistent exercise habits.

## Design and use

FitTrack uses a client-server architecture built with Flask. The frontend is developed using HTML, CSS, JavaScript, and Bootstrap, while user and workout data are stored in SQLite through SQLAlchemy.

Main features include:
- User registration, login, and logout
- Editable user profiles
- Workout logging and management
- Progress tracking
- Community ranking features with privacy controls
- Responsive interface for easier use across devices

## Group members

| UWA ID | Name | GitHub username |
|-------|------|-----------------|
| 24038858 | Giam Kie Shen | kiegiam |
| 24017328 | Steven Wang | docx1145 |
| 23902662) | Lucas Wu | whxgit665 |
| 23986795 | Tanish Khurana | tanish-khurana |

## Instructions to launch the application

### 1. Clone the repository
In the IDE of your choice, clone the repository from the following link
```bash
git clone https://github.com/kiegiam/CITS3403-Test-Repo.git
cd CITS3403-Test-Repo
```
### 2. Install the required dependencies

```bash
pip install -r requirements.txt
```
### 3. Run the application
```bash
python app.py
```
### 4. Open the application
After running the app.py file, the following link should appear, open it in your browser to enter the Fittrack site
```bash
http://127.0.0.1:5000
```


## Site Walkthrough
### 1. Index Page/ Landing Page
This page mainly serves as a introduction to our app. The page contains a breif into to our app and its purpose and serves to funnel users into the login and register pages
Security Note: This page will be mostly inaccessible to people who are already logged in. Anyone attempting to forcefully access the landing page will be logged out of their current session and shown a logout confirmation message.


### 2. Register page `/register`

The register page allows new users to create an account. Users must provide a name, email address, and valid password. Passwords must meet the required validation rules, and duplicate email addresses are not allowed. After successful registration, users are redirected to the login page. 

### Login page `/login`

The login page allows existing users to sign in. The page validates that the email and password fields are completed and that the email format is valid. If the login details are correct, the user is taken to the dashboard. If not, an error message is shown. Users who have forgotten their login information can apply for a password recovery email to be sent to their registered email address.

### Dashboard page `/dashboard`

The dashboard is the main landing page after login. It gives users a quick overview of their current fitness activity, including weekly workout activity, upcoming workout recommendations, and recent training sessions. It is designed to help users understand their progress at a glance.

### Profile page `/profile`

The profile page displays the user’s personal fitness profile, including their name, email, goal, location, member information, and profile picture. If no profile picture is uploaded, the site displays a default initials-based profile icon.

### Edit profile page `/profile/edit`

The edit profile page allows users to update their personal details, upload or remove a profile picture, and manage community privacy settings. Users can choose whether their profile information and fitness progress are visible in community areas such as the ranking page.

### Plans page `/plans`

The plans page provides workout plan options such as strength, cardio, and flexibility. Each plan directs users to the workout logging page with the chosen plan type attached, so workouts can be categorised correctly.

### Add workout page `/workouts/add`

The add workout page lets users create a new workout. Users first select the muscle groups or exercise category they are training, then add exercises and record exercise-specific details. Weighted exercises use reps and kilograms, bodyweight exercises use reps, and cardio exercises use distance-based tracking where appropriate. Users can also choose workout duration using either the live stopwatch or a manual duration entry, and select workout intensity manually.

### My Workouts page `/workouts`

The workouts page shows the user’s saved workout history. Users can review previous workouts, see workout type, duration, intensity, and notes, and access options to edit or manage individual workout records.

### Edit workout page `/workouts/<workout_id>/edit`

The edit workout page allows users to update an existing workout. Users can change the date, workout type, duration, intensity, and notes. Validation prevents users from setting a workout date later than the current date.

### Progress page `/progress`

The progress page summarises the user’s training progress over time. It helps users understand their workout consistency, training volume, and overall fitness activity trends.

### Ranking page `/ranking`

The ranking page shows community leaderboard information based on users who have enabled community fitness sharing. Users who hide their profile information appear as private users. If a user disables community fitness sharing, the page explains that community features are disabled and provides a link to the privacy settings in the edit profile page.

### Logout `/logout`

The logout route clears the user’s current session and returns them to the public home page.
