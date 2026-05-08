from flask import Blueprint, render_template, request, redirect, session
from werkzeug.utils import secure_filename
from database import get_connection
from flask import send_from_directory
import os






@upload_bp.route("/uploaded/<int:document_id>", methods=["GET"])
def uploaded_page(document_id):
    if "user" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM documents WHERE id = ?
    """, (document_id,))
    document = cursor.fetchone()

    if not document:
        conn.close()
        return redirect("/dashboard")

    cursor.execute("""
        SELECT id FROM users WHERE username = ?
    """, (session["user"],))
    user = cursor.fetchone()

    if not user or document["user_id"] != user["id"]:
        conn.close()
        return redirect("/dashboard")

    cursor.execute("""
        SELECT * FROM extracted_fields WHERE document_id = ?
    """, (document_id,))
    fields = cursor.fetchall()

    conn.close()

    return render_template(
        "uploaded.html",
        document=document,
        fields=fields
    )