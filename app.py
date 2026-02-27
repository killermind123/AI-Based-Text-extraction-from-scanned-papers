from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from database import init_db, get_connection
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Change this later for production

# Initialize database
init_db()

#home route
@app.route("/")
def home():
    if "user" in session:
        return render_template("dashboard.html", username=session["user"])
    return redirect("/login")

#signup route
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])

        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password)
            )
            conn.commit()
        except:
            conn.close()
            return "Username already exists"

        conn.close()
        return redirect("/login")

    return render_template("signup.html")

#Login route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        )
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user"] = username
            return redirect("/")
        else:
            return "Invalid Credentials"

    return render_template("login.html")

#logout rout
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

#upload get-route
@app.route("/upload", methods=["GET"])
def upload_page():
    if "user" not in session:
        return redirect("/login")
    return render_template("upload.html")

#upload Post-route
@app.route("/upload", methods=["POST"])
def upload_document():
    if "user" not in session:
        return redirect("/login")

    if "file" not in request.files:
        return "No file uploaded"

    file = request.files["file"]

    if file.filename == "":
        return "No selected file"

    filename = secure_filename(file.filename)

    # Save file to uploads folder
    upload_folder = "uploads"
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)

    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)

    # Get user ID
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username=?", (session["user"],))
    user = cursor.fetchone()

    if user:
        cursor.execute(
            "INSERT INTO documents (user_id, filename) VALUES (?, ?)",
            (user["id"], filename)
        )
        conn.commit()

    conn.close()

    return redirect("/")

@app.route("/uploaded", methods=["GET"])
def uploaded_page():
    if "user" not in session:
        return redirect("/login")
    return render_template("uploaded.html")


if __name__ == "__main__":
    app.run(debug=True)