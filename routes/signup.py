from flask import Blueprint, render_template, request, redirect, session
from werkzeug.security import generate_password_hash
from database import get_connection, execute

signup_bp = Blueprint("signup", __name__)

@signup_bp.route("/signup", methods=["GET"])
def signup_page():
    if "user" in session:
        return redirect("/")
    return render_template("signup.html")

@signup_bp.route("/signup", methods=["POST"])
def signup():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not username or not password:
        return render_template("signup.html", error="Please fill in all fields")

    if len(password) < 6:
        return render_template("signup.html", error="Password must be at least 6 characters")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        execute(cursor, """
            INSERT INTO users (username, password)
            VALUES (%s, %s)
        """, (username, generate_password_hash(password)))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect("/login")

    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return render_template("signup.html", error=f"Error: {str(e)}")