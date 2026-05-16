from flask import Blueprint, render_template, request, redirect, session, send_from_directory
from werkzeug.utils import secure_filename
from database import get_connection, row_to_dict, rows_to_dicts
import os

upload_bp = Blueprint("upload", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "tiff"}

processor = None
model = None


def get_model():
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
    text_lower = text.lower()
    if any(w in text_lower for w in ["receipt", "total", "subtotal", "change"]):
        return "receipt"
    elif any(w in text_lower for w in ["invoice", "due date", "bill to"]):
        return "invoice"
    elif any(w in text_lower for w in ["order", "order id", "order number"]):
        return "order"
    elif any(w in text_lower for w in ["contract", "agreement", "signed"]):
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
    upload_folder = "uploads"
    os.makedirs(upload_folder, exist_ok=True)
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = %s", (session["user"],))
    user = row_to_dict(cursor, cursor.fetchone())

    if not user:
        cursor.close()
        conn.close()
        return render_template("upload.html", error="User not found")

    cursor.execute("""
        INSERT INTO documents (user_id, file_name, file_path, processing_status)
        VALUES (%s, %s, %s, %s) RETURNING id
    """, (user["id"], filename, filepath, "processing"))

    document_id = cursor.fetchone()[0]
    conn.commit()

    try:
        # STEP 1 — Preprocess
        print("Step 1: Preprocessing image...")
        from ml_pipeline.preprocess import get_preprocessed
        processed_paths = get_preprocessed(filepath)
        processed_path = processed_paths[0]
        print(f"Preprocessed: {processed_path}")

        # STEP 2 — OCR
        print("Step 2: Running OCR...")
        from ml_pipeline.ocr import extract_text
        ocr_result = extract_text(processed_path)
        raw_text = ocr_result["raw_text"]
        print(f"OCR found {len(ocr_result['words'])} words")
        print(f"OCR boxes: {len(ocr_result['boxes'])}")

        cursor.execute("""
            UPDATE documents
            SET extracted_text = %s, processing_status = %s
            WHERE id = %s
        """, (raw_text, "processing", document_id))
        conn.commit()

        # STEP 3 — LayoutLMv3
        print("Step 3: Running LayoutLMv3...")
        extracted_fields = {}

        if ocr_result["boxes"] and len(ocr_result["boxes"]) > 0:
            try:
                from ml_pipeline.extractor import extract_fields
                proc, mdl = get_model()
                extracted_fields = extract_fields(
                    processed_path, ocr_result, proc, mdl
                )
                print(f"LayoutLMv3 extracted: {extracted_fields}")
            except Exception as e:
                print(f"LayoutLMv3 failed: {e}")
                from ml_pipeline.extractor import extract_fields_simple
                extracted_fields = extract_fields_simple(ocr_result)
        else:
            print("No boxes — using regex fallback...")
            from ml_pipeline.extractor import extract_fields_simple
            extracted_fields = extract_fields_simple(ocr_result)

        print(f"Final fields: {extracted_fields}")

        # STEP 4 — Post-process
        print("Step 4: Post-processing...")
        from ml_pipeline.postprocess import postprocess_fields
        from ml_pipeline.extractor import extract_fields_simple

        raw_values = {
            k: v["value"] if isinstance(v, dict) else v
            for k, v in extracted_fields.items()
        }
        cleaned_values = postprocess_fields(raw_values)
        print(f"Cleaned: {cleaned_values}")

        if not cleaned_values:
            print("No valid fields — trying regex...")
            regex_fields = extract_fields_simple(ocr_result)
            cleaned_values = postprocess_fields({
                k: v["value"] if isinstance(v, dict) else v
                for k, v in regex_fields.items()
            })
            print(f"Regex values: {cleaned_values}")

        if cleaned_values is None:
            cleaned_values = {}

        # STEP 5 — Document type
        doc_type = detect_document_type(raw_text)
        print(f"Document type: {doc_type}")

        # STEP 6 — Save to database
        print("Step 6: Saving to database...")
        cursor.execute("""
            UPDATE documents
            SET processing_status = %s, document_type = %s
            WHERE id = %s
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
                VALUES (%s, %s, %s, %s)
            """, (document_id, field_name, str(field_value), confidence))

        conn.commit()
        print("Extraction complete!")

    except Exception as e:
        print(f"Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        cursor.execute("""
            UPDATE documents SET processing_status = %s WHERE id = %s
        """, ("failed", document_id))
        conn.commit()

    finally:
        cursor.close()
        conn.close()

    return redirect(f"/uploaded/{document_id}")


# Serve uploaded images
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

    cursor.execute("SELECT * FROM documents WHERE id = %s", (document_id,))
    document = row_to_dict(cursor, cursor.fetchone())

    if not document:
        cursor.close()
        conn.close()
        return redirect("/")

    cursor.execute("SELECT id FROM users WHERE username = %s", (session["user"],))
    user = row_to_dict(cursor, cursor.fetchone())

    if not user or document["user_id"] != user["id"]:
        cursor.close()
        conn.close()
        return redirect("/")

    cursor.execute("""
        SELECT * FROM extracted_fields WHERE document_id = %s
    """, (document_id,))
    fields = rows_to_dicts(cursor, cursor.fetchall())

    cursor.close()
    conn.close()

    return render_template(
        "uploaded.html",
        document=document,
        fields=fields
    )