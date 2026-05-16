from flask import Blueprint, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_connection, execute, fetchone, fetchall

profile_bp = Blueprint("profile", __name__)


def get_profile_data(cursor, user_id):
    execute(cursor, """
        SELECT COUNT(*) as total FROM documents WHERE user_id = %s
    """, (user_id,))
    total_docs = fetchone(cursor)["total"]

    execute(cursor, """
        SELECT COUNT(*) as total FROM documents
        WHERE user_id = %s AND processing_status = 'processed'
    """, (user_id,))
    processed_docs = fetchone(cursor)["total"]

    execute(cursor, """
        SELECT COUNT(*) as total FROM documents
        WHERE user_id = %s AND processing_status = 'failed'
    """, (user_id,))
    failed_docs = fetchone(cursor)["total"]

    execute(cursor, """
        SELECT d.id, d.file_name, d.upload_time,
               d.processing_status, d.document_type,
               COUNT(ef.id) as field_count
        FROM documents d
        LEFT JOIN extracted_fields ef ON d.id = ef.document_id
        WHERE d.user_id = %s
        GROUP BY d.id
        ORDER BY d.upload_time DESC
        LIMIT 10
    """, (user_id,))
    documents = fetchall(cursor)

    return total_docs, processed_docs, failed_docs, documents


@profile_bp.route("/profile", methods=["GET"])
def profile_page():
    if "user" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor()

    execute(cursor, """
        SELECT id, username, email, created_at
        FROM users WHERE username = %s
    """, (session["user"],))
    user = fetchone(cursor)

    if not user:
        cursor.close()
        conn.close()
        return redirect("/login")

    total_docs, processed_docs, failed_docs, documents = get_profile_data(
        cursor, user["id"]
    )

    cursor.close()
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

    execute(cursor, "SELECT * FROM users WHERE username = %s", (session["user"],))
    user = fetchone(cursor)

    if not user:
        cursor.close()
        conn.close()
        return redirect("/login")

    errors = []
    success = []

    if new_username and new_username != user["username"]:
        execute(cursor, """
            SELECT id FROM users WHERE username = %s AND id != %s
        """, (new_username, user["id"]))
        if fetchone(cursor):
            errors.append("Username already taken")
        else:
            execute(cursor, """
                UPDATE users SET username = %s WHERE id = %s
            """, (new_username, user["id"]))
            session["user"] = new_username
            success.append("Username updated successfully")

    if new_email and new_email != user["email"]:
        execute(cursor, """
            UPDATE users SET email = %s WHERE id = %s
        """, (new_email, user["id"]))
        success.append("Email updated successfully")

    if current_password or new_password or confirm_password:
        if not check_password_hash(user["password"], current_password):
            errors.append("Current password is incorrect")
        elif new_password != confirm_password:
            errors.append("New passwords do not match")
        elif len(new_password) < 6:
            errors.append("Password must be at least 6 characters")
        else:
            execute(cursor, """
                UPDATE users SET password = %s WHERE id = %s
            """, (generate_password_hash(new_password), user["id"]))
            success.append("Password updated successfully")

    conn.commit()

    execute(cursor, """
        SELECT id, username, email, created_at FROM users WHERE id = %s
    """, (user["id"],))
    updated_user = fetchone(cursor)

    total_docs, processed_docs, failed_docs, documents = get_profile_data(
        cursor, updated_user["id"]
    )

    cursor.close()
    conn.close()

    return render_template("profile.html",
                           user=updated_user,
                           total_docs=total_docs,
                           processed_docs=processed_docs,
                           failed_docs=failed_docs,
                           documents=documents,
                           errors=errors,
                           success=success)