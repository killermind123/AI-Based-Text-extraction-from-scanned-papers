from flask import Blueprint, render_template, session, redirect
from database import get_connection, execute, fetchone, fetchall

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/dashboard")
def dashboard():
    if "user" not in session:
        return render_template("dashboard.html")

    conn = get_connection()
    cursor = conn.cursor()

    execute(cursor, "SELECT id FROM users WHERE username = %s", (session["user"],))
    user = fetchone(cursor)

    if not user:
        cursor.close()
        conn.close()
        return redirect("/login")

    user_id = user["id"]

    execute(cursor, "SELECT COUNT(*) as total FROM documents WHERE user_id = %s", (user_id,))
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
        SELECT COUNT(*) as total FROM extracted_fields ef
        JOIN documents d ON ef.document_id = d.id
        WHERE d.user_id = %s
    """, (user_id,))
    total_fields = fetchone(cursor)["total"]

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

    cursor.close()
    conn.close()

    return render_template("dashboard.html",
                           total_docs=total_docs,
                           processed_docs=processed_docs,
                           failed_docs=failed_docs,
                           total_fields=total_fields,
                           documents=documents)