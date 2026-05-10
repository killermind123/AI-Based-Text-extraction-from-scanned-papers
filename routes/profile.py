from flask import Blueprint, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_connection

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/profile", methods=["GET"])
def profile_page():
    if "user" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor()

    # Get user details
    cursor.execute("""
        SELECT id, username, email, created_at 
        FROM users WHERE username = ?
    """, (session["user"],))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return redirect("/login")

    # Get document statistics
    cursor.execute("""
        SELECT COUNT(*) as total FROM documents 
        WHERE user_id = ?
    """, (user["id"],))
    total_docs = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) as total FROM documents 
        WHERE user_id = ? AND processing_status = 'processed'
    """, (user["id"],))
    processed_docs = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) as total FROM documents 
        WHERE user_id = ? AND processing_status = 'failed'
    """, (user["id"],))
    failed_docs = cursor.fetchone()["total"]

    # Get recent documents
    cursor.execute("""
        SELECT d.id, d.file_name, d.upload_time, 
               d.processing_status, d.document_type,
               COUNT(ef.id) as field_count
        FROM documents d
        LEFT JOIN extracted_fields ef ON d.id = ef.document_id
        WHERE d.user_id = ?
        GROUP BY d.id
        ORDER BY d.upload_time DESC
        LIMIT 10
    """, (user["id"],))
    documents = cursor.fetchall()

    conn.close()

    return render_template("profile.html",
                         user=user,
                         total_docs=total_docs,
                         processed_docs=processed_docs,
                         failed_docs=failed_docs,
                         documents=documents)


@profile_bp.route("/profile/update", methods=["POST"])
def update_profile():
    if "user" not in session:
        return redirect("/login")

    new_username = request.form.get("username", "").strip()
    new_email = request.form.get("email", "").strip()
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM users WHERE username = ?
    """, (session["user"],))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return redirect("/login")

    errors = []
    success = []

    # Update username and email
    if new_username and new_username != user["username"]:
        # Check if username already taken
        cursor.execute("""
            SELECT id FROM users WHERE username = ? AND id != ?
        """, (new_username, user["id"]))
        if cursor.fetchone():
            errors.append("Username already taken")
        else:
            cursor.execute("""
                UPDATE users SET username = ? WHERE id = ?
            """, (new_username, user["id"]))
            session["user"] = new_username
            success.append("Username updated successfully")

    if new_email and new_email != user["email"]:
        cursor.execute("""
            UPDATE users SET email = ? WHERE id = ?
        """, (new_email, user["id"]))
        success.append("Email updated successfully")

    # Update password
    if current_password or new_password or confirm_password:
        if not check_password_hash(user["password"], current_password):
            errors.append("Current password is incorrect")
        elif new_password != confirm_password:
            errors.append("New passwords do not match")
        elif len(new_password) < 6:
            errors.append("Password must be at least 6 characters")
        else:
            cursor.execute("""
                UPDATE users SET password = ? WHERE id = ?
            """, (generate_password_hash(new_password), user["id"]))
            success.append("Password updated successfully")

    conn.commit()

    # Refresh user data
    cursor.execute("""
        SELECT id, username, email, created_at 
        FROM users WHERE id = ?
    """, (user["id"],))
    updated_user = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) as total FROM documents WHERE user_id = ?
    """, (user["id"],))
    total_docs = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) as total FROM documents 
        WHERE user_id = ? AND processing_status = 'processed'
    """, (user["id"],))
    processed_docs = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) as total FROM documents 
        WHERE user_id = ? AND processing_status = 'failed'
    """, (user["id"],))
    failed_docs = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT d.id, d.file_name, d.upload_time,
               d.processing_status, d.document_type,
               COUNT(ef.id) as field_count
        FROM documents d
        LEFT JOIN extracted_fields ef ON d.id = ef.document_id
        WHERE d.user_id = ?
        GROUP BY d.id
        ORDER BY d.upload_time DESC
        LIMIT 10
    """, (user["id"],))
    documents = cursor.fetchall()

    conn.close()

    return render_template("profile.html",
                         user=updated_user,
                         total_docs=total_docs,
                         processed_docs=processed_docs,
                         failed_docs=failed_docs,
                         documents=documents,
                         errors=errors,
                         success=success)