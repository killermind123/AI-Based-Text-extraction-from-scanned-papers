from flask import Blueprint, render_template, request, redirect, session, send_from_directory
from werkzeug.utils import secure_filename
from database import get_connection, execute, fetchone, fetchall, is_postgres
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
            "ml_pipeline", "models", "layoutlmv3-cord-funsd"
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


def should_preprocess(filepath):
    """
    Check if image needs preprocessing.
    Clean digital images should skip preprocessing.
    """
    import cv2
    img = cv2.imread(filepath)
    if img is None:
        return True
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    print(f"Image blur score: {blur_score:.2f}")
    # High blur score = sharp clean image = skip preprocessing
    return blur_score < 100


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

    execute(cursor, "SELECT id FROM users WHERE username = %s", (session["user"],))
    user = fetchone(cursor)

    if not user:
        cursor.close()
        conn.close()
        return render_template("upload.html", error="User not found")

    if is_postgres():
        execute(cursor, """
            INSERT INTO documents (user_id, file_name, file_path, processing_status)
            VALUES (%s, %s, %s, %s) RETURNING id
        """, (user["id"], filename, filepath, "processing"))
        document_id = cursor.fetchone()[0]
    else:
        execute(cursor, """
            INSERT INTO documents (user_id, file_name, file_path, processing_status)
            VALUES (%s, %s, %s, %s)
        """, (user["id"], filename, filepath, "processing"))
        document_id = cursor.lastrowid

    conn.commit()

    try:
        # ===================================
        # STEP 1 — Smart Preprocessing
        # ===================================
        print("Step 1: Checking image quality...")
        from ml_pipeline.preprocess import get_preprocessed

        if should_preprocess(filepath):
            print("Poor quality image — preprocessing...")
            processed_paths = get_preprocessed(filepath)
            processed_path = processed_paths[0]
        else:
            print("Clean image — skipping preprocessing...")
            processed_path = filepath

        print(f"Using: {processed_path}")

        # ===================================
        # STEP 2 — OCR
        # ===================================
        print("Step 2: Running OCR...")
        from ml_pipeline.ocr import extract_text
        ocr_result = extract_text(processed_path)
        raw_text = ocr_result["raw_text"]
        print(f"OCR found {len(ocr_result['words'])} words")
        print(f"OCR boxes: {len(ocr_result['boxes'])}")
        print(f"OCR preview: {raw_text[:200]}")

        execute(cursor, """
            UPDATE documents
            SET extracted_text = %s, processing_status = %s
            WHERE id = %s
        """, (raw_text, "processing", document_id))
        conn.commit()

        # ===================================
        # STEP 3 — Regex extraction (primary)
        # ===================================
        print("Step 3: Running regex extraction...")
        from ml_pipeline.extractor import extract_fields_simple
        regex_fields = extract_fields_simple(ocr_result)
        print(f"Regex extracted: {regex_fields}")

        # ===================================
        # STEP 4 — LayoutLMv3 (supplement)
        # ===================================
        print("Step 4: Running LayoutLMv3...")
        layoutlm_fields = {}

        if ocr_result["boxes"] and len(ocr_result["boxes"]) > 0:
            try:
                from ml_pipeline.extractor import extract_fields
                proc, mdl = get_model()
                layoutlm_fields = extract_fields(
                    processed_path, ocr_result, proc, mdl
                )
                print(f"LayoutLMv3 extracted: {layoutlm_fields}")
            except Exception as e:
                print(f"LayoutLMv3 failed: {e}")

        # Merge — regex takes priority, LayoutLMv3 fills gaps
        extracted_fields = {**layoutlm_fields, **regex_fields}
        print(f"Merged fields: {extracted_fields}")

        # ===================================
        # STEP 5 — Post-process
        # ===================================
        print("Step 5: Post-processing...")
        from ml_pipeline.postprocess import postprocess_fields

        raw_values = {
            k: v["value"] if isinstance(v, dict) else v
            for k, v in extracted_fields.items()
        }
        cleaned_values = postprocess_fields(raw_values)
        print(f"Cleaned: {cleaned_values}")

        # If still nothing — try raw regex on original file
        if not cleaned_values:
            print("Nothing found — trying OCR on original file...")
            ocr_original = extract_text(filepath)
            regex_original = extract_fields_simple(ocr_original)
            cleaned_values = postprocess_fields({
                k: v["value"] if isinstance(v, dict) else v
                for k, v in regex_original.items()
            })
            print(f"Original file regex: {cleaned_values}")

        if cleaned_values is None:
            cleaned_values = {}

        # ===================================
        # STEP 6 — Document type
        # ===================================
        doc_type = detect_document_type(raw_text)
        print(f"Document type: {doc_type}")

        # ===================================
        # STEP 7 — Save to database
        # ===================================
        print("Step 7: Saving to database...")
        execute(cursor, """
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

            execute(cursor, """
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
        execute(cursor, """
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


# Results page
@upload_bp.route("/uploaded/<int:document_id>", methods=["GET"])
def uploaded_page(document_id):
    if "user" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor()

    execute(cursor, "SELECT * FROM documents WHERE id = %s", (document_id,))
    document = fetchone(cursor)

    if not document:
        cursor.close()
        conn.close()
        return redirect("/")

    execute(cursor, "SELECT id FROM users WHERE username = %s", (session["user"],))
    user = fetchone(cursor)

    if not user or document["user_id"] != user["id"]:
        cursor.close()
        conn.close()
        return redirect("/")

    execute(cursor, """
        SELECT * FROM extracted_fields WHERE document_id = %s
    """, (document_id,))
    fields = fetchall(cursor)

    cursor.close()
    conn.close()

    return render_template(
        "uploaded.html",
        document=document,
        fields=fields
    )


# Debug route
@upload_bp.route("/debug/<int:document_id>")
def debug_ocr(document_id):
    if "user" not in session:
        return redirect("/login")

    from ml_pipeline.ocr import extract_text
    from ml_pipeline.preprocess import get_preprocessed

    conn = get_connection()
    cursor = conn.cursor()
    execute(cursor, "SELECT * FROM documents WHERE id = %s", (document_id,))
    doc = fetchone(cursor)
    cursor.close()
    conn.close()

    if not doc:
        return "Document not found"

    needs_preprocessing = should_preprocess(doc["file_path"])

    ocr_original = extract_text(doc["file_path"])
    processed_paths = get_preprocessed(doc["file_path"])
    ocr_processed = extract_text(processed_paths[0])

    from ml_pipeline.extractor import extract_fields_simple
    regex_original = extract_fields_simple(ocr_original)
    regex_processed = extract_fields_simple(ocr_processed)

    return f"""
    <html><body style="font-family:monospace; padding:20px">
    <h2>Image Quality</h2>
    <p>Needs preprocessing: <b>{needs_preprocessing}</b></p>
    <hr>
    <h2>Original OCR ({len(ocr_original['words'])} words)</h2>
    <pre style="background:#f5f5f5;padding:10px">{ocr_original['raw_text']}</pre>
    <h3>Regex on original:</h3>
    <pre style="background:#e8f5e9;padding:10px">{regex_original}</pre>
    <hr>
    <h2>Preprocessed OCR ({len(ocr_processed['words'])} words)</h2>
    <pre style="background:#f5f5f5;padding:10px">{ocr_processed['raw_text']}</pre>
    <h3>Regex on preprocessed:</h3>
    <pre style="background:#e8f5e9;padding:10px">{regex_processed}</pre>
    </body></html>
    """