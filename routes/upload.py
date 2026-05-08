from flask import Blueprint, render_template, request, redirect, session
from werkzeug.utils import secure_filename
from database import get_connection
from flask import send_from_directory
import os

upload_bp = Blueprint("upload", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "tiff"}

# Load model once when server starts
processor = None
model = None

def get_model():
    """
    Load LayoutLMv3 model once and reuse.
    """
    global processor, model
    if processor is None or model is None:
        from ml_pipeline.extractor import load_model
        fine_tuned_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "ml_pipeline", "models", "layoutlmv3-finetuned"
        )
        print(f"Looking for model at: {fine_tuned_path}")
        processor, model = load_model(fine_tuned_path)
        print("Model loaded successfully!")
    return processor, model


def allowed_file(filename):
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def detect_document_type(text):
    """Simple document type detection based on keywords."""
    text_lower = text.lower()
    if any(word in text_lower for word in ["receipt", "total", "subtotal", "change"]):
        return "receipt"
    elif any(word in text_lower for word in ["invoice", "due date", "bill to"]):
        return "invoice"
    elif any(word in text_lower for word in ["order", "order id", "order number"]):
        return "order"
    elif any(word in text_lower for word in ["contract", "agreement", "signed"]):
        return "contract"
    else:
        return "document"


# GET - Upload page
@upload_bp.route("/upload", methods=["GET"])
def upload_page():
    if "user" not in session:
        return redirect("/login")
    return render_template("upload.html")


# POST - Handle upload
@upload_bp.route("/upload", methods=["POST"])
def upload_document():
    if "user" not in session:
        return redirect("/login")

    if "file" not in request.files:
        return render_template("upload.html", error="No file uploaded")

    file = request.files["file"]

    if file.filename == "":
        return render_template("upload.html", error="No file selected")

    if not allowed_file(file.filename):
        return render_template("upload.html",
                             error="Invalid file type. Upload PNG, JPG, PDF or TIFF")

    filename = secure_filename(file.filename)

    # Save file
    upload_folder = "uploads"
    os.makedirs(upload_folder, exist_ok=True)
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)

    # DB connection
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username=?", (session["user"],))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return render_template("upload.html", error="User not found")

    # Insert document record
    cursor.execute("""
        INSERT INTO documents (user_id, file_name, file_path, processing_status)
        VALUES (?, ?, ?, ?)
    """, (user["id"], filename, filepath, "processing"))

    conn.commit()
    document_id = cursor.lastrowid

    try:
        # ===================================
        # STEP 1 — Preprocess image
        # ===================================
        print("Step 1: Preprocessing image...")
        from ml_pipeline.preprocess import get_preprocessed
        processed_paths = get_preprocessed(filepath)
        processed_path = processed_paths[0]
        print(f"Preprocessed image saved to: {processed_path}")

        # ===================================
        # STEP 2 — OCR
        # ===================================
        print("Step 2: Running OCR...")
        from ml_pipeline.ocr import extract_text
        ocr_result = extract_text(processed_path)
        raw_text = ocr_result["raw_text"]

        # Debug prints
        print(f"OCR extracted {len(ocr_result['words'])} words")
        print(f"OCR boxes count: {len(ocr_result['boxes'])}")
        print(f"First 3 words: {ocr_result['words'][:3]}")
        print(f"First 3 boxes: {ocr_result['boxes'][:3]}")

        # Update raw text in DB
        cursor.execute("""
            UPDATE documents
            SET extracted_text = ?, processing_status = ?
            WHERE id = ?
        """, (raw_text, "processing", document_id))
        conn.commit()

        # ===================================
        # STEP 3 — LayoutLMv3 Extraction
        # ===================================
        print("Step 3: Running LayoutLMv3 extraction...")

        extracted_fields = {}

        if ocr_result["boxes"] and len(ocr_result["boxes"]) > 0:
            try:
                from ml_pipeline.extractor import extract_fields
                proc, mdl = get_model()
                extracted_fields = extract_fields(
                    processed_path,
                    ocr_result,
                    proc,
                    mdl
                )
                print(f"LayoutLMv3 extracted: {extracted_fields}")

            except Exception as e:
                print(f"LayoutLMv3 failed, using fallback: {e}")
                from ml_pipeline.extractor import extract_fields_simple
                extracted_fields = extract_fields_simple(ocr_result)
        else:
            print("No boxes from OCR, using regex fallback...")
            from ml_pipeline.extractor import extract_fields_simple
            extracted_fields = extract_fields_simple(ocr_result)

        print(f"Final extracted fields: {extracted_fields}")
        
        # ===================================
        # STEP 4 — Post-process fields
        # ===================================
        print("Step 4: Post-processing fields...")
        from ml_pipeline.postprocess import postprocess_fields
        from ml_pipeline.extractor import extract_fields_simple

        raw_values = {
                k: v["value"] if isinstance(v, dict) else v
                for k, v in extracted_fields.items()
        }
        cleaned_values = postprocess_fields(raw_values)
        print(f"Cleaned values from LayoutLMv3: {cleaned_values}")

        # If LayoutLMv3 gave no valid results — try regex fallback
        if not cleaned_values:
            print("LayoutLMv3 gave no valid fields — trying regex fallback...")
            regex_fields = extract_fields_simple(ocr_result)
            raw_regex_values = {
                k: v["value"] if isinstance(v, dict) else v
                for k, v in regex_fields.items()
            }
            cleaned_values = postprocess_fields(raw_regex_values)
            print(f"Regex fallback values: {cleaned_values}")

        # ===================================
        # STEP 5 — Detect document type
        # ===================================
        doc_type = detect_document_type(raw_text)
        print(f"Document type: {doc_type}")

        # ===================================
        # STEP 6 — Save to database
        # ===================================
        print("Step 6: Saving to database...")

        cursor.execute("""
            UPDATE documents
            SET processing_status = ?, document_type = ?
            WHERE id = ?
        """, ("processed", doc_type, document_id))

        for field_name, field_value in cleaned_values.items():
            confidence = 0.75
            if field_name in extracted_fields:
                field_data = extracted_fields[field_name]
                if isinstance(field_data, dict):
                    confidence = field_data.get("confidence", 0.75)

            cursor.execute("""
                INSERT INTO extracted_fields
                (document_id, field_name, field_value, confidence)
                VALUES (?, ?, ?, ?)
            """, (document_id, field_name, str(field_value), confidence))

        conn.commit()
        print("Extraction complete!")

    except Exception as e:
        print(f"Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        cursor.execute("""
            UPDATE documents SET processing_status = ? WHERE id = ?
        """, ("failed", document_id))
        conn.commit()

    finally:
        conn.close()

    return redirect(f"/uploaded/{document_id}")


# Route to serve uploaded images
@upload_bp.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory("uploads", filename)


# GET - Results page
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