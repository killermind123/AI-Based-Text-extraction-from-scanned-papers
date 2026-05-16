from flask import Blueprint, render_template, request, redirect, session
from werkzeug.security import check_password_hash
from database import get_connection, execute, fetchone

login_bp = Blueprint("login", __name__)

@login_bp.route("/login", methods=["GET"])
def login_page():
    if "user" in session:
        return redirect("/dashboard")
    return render_template("login.html")

@login_bp.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not username or not password:
        return render_template("login.html", error="Please fill in all fields")

    conn = get_connection()
    cursor = conn.cursor()

    execute(cursor, "SELECT * FROM users WHERE username = %s", (username,))
    user = fetchone(cursor)

    cursor.close()
    conn.close()

    if not user:
        return render_template("login.html", error="Invalid username or password")

    if not check_password_hash(user["password"], password):
        return render_template("login.html", error="Invalid username or password")

    session["user"] = user["username"]
    return redirect("/dashboard")