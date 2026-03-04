from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from database import init_db, get_connection
import pytesseract
from PIL import Image
import os
import re



app = Flask(__name__)
app.secret_key = "supersecretkey"  # Change this later for production

#to extract the specific field like orderid, address, date, total, signature
def extract_structured_fields(text):
    fields = {}

    # ==========================
    # Order ID
    # ==========================
    order_match = re.search(
        r'Order\s*ID[:\s]*([A-Z0-9\-]+)',
        text,
        re.IGNORECASE
    )
    if order_match:
        fields["order_id"] = order_match.group(1)

    # ==========================
    # Invoice Number
    # ==========================
    invoice_match = re.search(
        r'Invoice\s*(Number|No\.?)?[:\s]*([A-Z0-9\-]+)',
        text,
        re.IGNORECASE
    )
    if invoice_match:
        fields["invoice"] = invoice_match.group(2)

    # ==========================
    # Date
    # ==========================
    date_match = re.search(
        r'Date[:\s]*([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4})',
        text,
        re.IGNORECASE
    )
    if date_match:
        fields["date"] = date_match.group(1)

    # ==========================
    # Total Amount
    # ==========================
    total_match = re.search(
        r'Total[:\s]*\$?([0-9,.]+)',
        text,
        re.IGNORECASE
    )
    if total_match:
        fields["total"] = total_match.group(1)

    # ==========================
    # Address (Multi-line capture)
    # ==========================
    address_match = re.search(
        r'Address[:\s]*([\s\S]{10,300})',
        text,
        re.IGNORECASE
    )
    if address_match:
        address = address_match.group(1).strip()

        # Stop address at double newline or keyword
        address = re.split(r'\n\s*\n|Signature|Total|Invoice|Date', address, flags=re.IGNORECASE)[0]
        fields["address"] = address.strip()

    # ==========================
    # Signature
    # ==========================
    signature_match = re.search(
        r'Signature[:\s]*([\s\S]{5,200})',
        text,
        re.IGNORECASE
    )
    if signature_match:
        signature = signature_match.group(1).strip()

        # Stop at next section if detected
        signature = re.split(r'\n\s*\n|Total|Invoice|Date|Order', signature, flags=re.IGNORECASE)[0]
        fields["signature"] = signature.strip()

    return fields

# Initialize database
init_db()

# getting the tesseract path from the local device
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\S22247228\Desktop\ocr\tesseract.exe"

#home route
@app.route("/")
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
#Profile Route
@app.route("/Profile", methods= ["GET"])
def profile():
    if "user" in session:
        return render_template("Profile.html", username=session["user"])
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

    # -----------------------------------
    # Save File
    # -----------------------------------
    upload_folder = "uploads"
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)

    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)

    # -----------------------------------
    # DB Connection
    # -----------------------------------
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM users WHERE username=?",
        (session["user"],)
    )
    user = cursor.fetchone()

    if not user:
        conn.close()
        return "User not found"

    # -----------------------------------
    # Insert Document (Status = Processing)
    # -----------------------------------
    cursor.execute("""
        INSERT INTO documents (user_id, file_name, file_path, status)
        VALUES (?, ?, ?, ?)
    """, (user["id"], filename, filepath, "processing"))

    conn.commit()

    document_id = cursor.lastrowid

    # ===================================
    # 🔥 OCR + AI EXTRACTION
    # ===================================
    try:

        # ✅ OCR
        text = pytesseract.image_to_string(Image.open(filepath))

        # ✅ Update raw text
        cursor.execute("""
            UPDATE documents
            SET extracted_text = ?, status = ?
            WHERE id = ?
        """, (text, "processed", document_id))

        conn.commit()

        # ===================================
        # 🔥 STRUCTURED FIELD EXTRACTION
        # ===================================
        structured_data = extract_structured_fields(text)

        # ===================================
        # 🔥 INSERT EXTRACTED FIELDS INTO DB
        # ===================================
        for field_name, field_value in structured_data.items():

            cursor.execute("""
                INSERT INTO extracted_fields 
                (document_id, field_name, field_value, confidence)
                VALUES (?, ?, ?, ?)
            """, (
                document_id,
                field_name,
                str(field_value),
                0.95  # You can improve this later
            ))

        conn.commit()

    except Exception as e:
        print("OCR Error:", e)

        cursor.execute("""
            UPDATE documents
            SET status = ?
            WHERE id = ?
        """, ("failed", document_id))

        conn.commit()

    conn.close()

    return redirect("/")

@app.route("/uploaded", methods=["GET"])
def uploaded_page():
    if "user" not in session:
        return redirect("/login")
    
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM documents ")
    user = cursor.fetchone()
    return render_template("uploaded.html", name=user["filename"])


if __name__ == "__main__":
    app.run(debug=True)