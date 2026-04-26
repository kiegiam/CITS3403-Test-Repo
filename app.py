from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
app.secret_key = "dev-secret-key"

DEMO_EMAIL = "demo@fittrack.com"
DEMO_PASSWORD = "password123"


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

    return render_template("dashboard.html", email=session["user_email"])

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
