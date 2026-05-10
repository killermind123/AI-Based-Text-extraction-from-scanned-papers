from flask import Blueprint, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from database import init_db, get_connection
import pytesseract
from PIL import Image
import os
import re

dashboard_bp = Blueprint("dashboard", __name__)

#dashboard route
@dashboard_bp.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor()

    # Get user ID
    cursor.execute("SELECT id FROM users WHERE username=?", (session["user"],))
    user = cursor.fetchone()

    documents = []

    if user:
        cursor.execute("""
            SELECT * FROM documents
            WHERE user_id = ?
            ORDER BY upload_time DESC
        """, (user["id"],))

        docs = cursor.fetchall()

        for doc in docs:
            # Convert sqlite3.Row → dictionary
            doc_dict = dict(doc)

            # Fetch extracted fields
            cursor.execute("""
                SELECT field_name, field_value
                FROM extracted_fields
                WHERE document_id = ?
            """, (doc["id"],))

            doc_dict["fields"] = cursor.fetchall()

            documents.append(doc_dict)

    conn.close()

    return render_template(
        "dashboard.html",
        documents=documents,
        username=session["user"]
    )