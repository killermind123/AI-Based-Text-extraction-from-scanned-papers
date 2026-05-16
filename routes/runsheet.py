from flask import Blueprint, render_template, request, redirect, session, send_from_directory
from werkzeug.utils import secure_filename
import os
import re
import json

runsheet_bp = Blueprint("runsheet", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "tiff"}
RUNSHEET_OUTPUT_FOLDER = "runsheet_outputs"


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def safe_crop(img, x0, y0, x1, y1):
    """Crop with clamped coordinates to avoid PIL errors."""
    w, h = img.width, img.height
    x0 = max(0, min(int(x0), w - 1))
    y0 = max(0, min(int(y0), h - 1))
    x1 = max(x0 + 1, min(int(x1), w))
    y1 = max(y0 + 1, min(int(y1), h))
    return img.crop((x0, y0, x1, y1))


# ─────────────────────────────────────────────
# UPLOAD PAGE — GET
# ─────────────────────────────────────────────

@runsheet_bp.route("/runsheet", methods=["GET"])
def runsheet_page():
    if "user" not in session:
        return redirect("/login")
    return render_template("runsheet_upload.html")


# ─────────────────────────────────────────────
# PROCESS RUNSHEET — POST
# ─────────────────────────────────────────────

@runsheet_bp.route("/runsheet", methods=["POST"])
def process_runsheet():
    if "user" not in session:
        return redirect("/login")

    if "file" not in request.files:
        return render_template("runsheet_upload.html", error="No file uploaded")

    file = request.files["file"]

    if file.filename == "":
        return render_template("runsheet_upload.html", error="No file selected")

    if not allowed_file(file.filename):
        return render_template("runsheet_upload.html",
                               error="Invalid file type. Upload PNG, JPG, PDF or TIFF")

    # Save upload
    filename = secure_filename(file.filename)
    upload_folder = "uploads"
    os.makedirs(upload_folder, exist_ok=True)
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)

    # Create a unique output folder for this job
    import time
    job_id = str(int(time.time()))
    output_dir = os.path.join(RUNSHEET_OUTPUT_FOLDER, job_id)
    os.makedirs(output_dir, exist_ok=True)

    try:
        from PIL import Image
        import numpy as np

        ext = filename.rsplit(".", 1)[1].lower()

        if ext == "pdf":
            try:
                from pdf2image import convert_from_path
                pages = convert_from_path(filepath, dpi=200)
            except Exception as e:
                return render_template("runsheet_upload.html",
                                       error=f"PDF conversion failed: {e}. Install pdf2image and poppler.")
        else:
            pages = [Image.open(filepath).convert("RGB")]

        all_orders = []

        for page_num, page_img in enumerate(pages, start=1):
            orders = _process_page(page_img, output_dir, page_num, job_id)
            all_orders.extend(orders)

        # Save a JSON manifest for the results page
        manifest_path = os.path.join(output_dir, "manifest.json")
        with open(manifest_path, "w") as f:
            json.dump({"orders": all_orders, "source": filename}, f)

        return redirect(f"/runsheet/results/{job_id}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        return render_template("runsheet_upload.html",
                               error=f"Processing failed: {str(e)}")


def _process_page(img, output_dir, page_num, job_id):
    """Run the runsheet extractor on one page, save crops, return order list."""
    import numpy as np
    import pytesseract
    from PIL import Image

    img = img.convert("RGB")
    arr = np.array(img)
    w, h = img.width, img.height
    orders_data = []

    # ── Detect order blocks by green left border ──
    def is_green(r, g, b): return (g - r) > 40 and g > 120 and b < 150
    def is_blue(r, g, b):  return b > 150 and r < 100 and g < 130

    green_id_rows = []
    for y in range(h):
        row = arr[y, 0:min(100, w)]
        cnt = sum(1 for px in row if is_green(int(px[0]), int(px[1]), int(px[2])))
        if cnt > 20:
            green_id_rows.append(y)

    def group_rows(rows, gap=40, min_height=5):
        if not rows:
            return []
        groups, start, prev = [], rows[0], rows[0]
        for r in rows[1:]:
            if r - prev > gap:
                if prev - start >= min_height:
                    groups.append((start, prev))
                start = r
            prev = r
        if prev - start >= min_height:
            groups.append((start, prev))
        return groups

    green_bands = group_rows(green_id_rows)

    for i, (gy0, gy1) in enumerate(green_bands):
        # Ensure band is valid
        if gy1 <= gy0:
            continue

        # Find blue box below green band
        blue_start = blue_end = None
        in_blue = False
        search_end = min(gy1 + 120, h)
        for y in range(gy1 + 1, search_end):
            row_slice = arr[y, w // 2:w]
            cnt = sum(1 for px in row_slice if is_blue(int(px[0]), int(px[1]), int(px[2])))
            if cnt > 5:
                if not in_blue:
                    blue_start = y
                    in_blue = True
                blue_end = y
            elif in_blue and blue_end is not None and y - blue_end > 5:
                break

        # ── OCR helpers ──
        def green_mask_ocr(x0, y0, x1, y1, whitelist=None, psm=7):
            crop = safe_crop(img, x0, y0, x1, y1)
            ca = np.array(crop).astype(int)
            mask = ((ca[:, :, 1] - ca[:, :, 0]) > 40) & (ca[:, :, 1] > 120)
            cl = ca.copy()
            cl[mask] = [255, 255, 255]
            gray = Image.fromarray(cl.astype(np.uint8)).convert('L')
            if gray.width == 0 or gray.height == 0:
                return ""
            big = gray.resize((gray.width * 4, gray.height * 4), Image.LANCZOS)
            cfg = f'--psm {psm}'
            if whitelist:
                cfg += f' -c tessedit_char_whitelist={whitelist}'
            return pytesseract.image_to_string(big, config=cfg).strip()

        def is_redacted(x0, y0, x1, y1):
            x0c = max(0, int(x0))
            y0c = max(0, int(y0))
            x1c = min(w, int(x1))
            y1c = min(h, int(y1))
            if x1c <= x0c or y1c <= y0c:
                return False
            region = arr[y0c:y1c, x0c:x1c]
            total = region.shape[0] * region.shape[1]
            if total == 0:
                return False
            red = np.sum(
                (region[:, :, 0] > 180) &
                (region[:, :, 1] < 80) &
                (region[:, :, 2] < 80)
            )
            return (red / total) > 0.3

        # ── OCR: Order ID ──
        order_id = "UNKNOWN"
        if not is_redacted(6, gy0, 73, gy1):
            raw = green_mask_ocr(6, gy0, 73, gy1, whitelist='0123456789', psm=8)
            if raw:
                order_id = raw

        # ── OCR: Name ──
        name = "UNKNOWN"
        if not is_redacted(78, gy0, 375, gy1):
            raw = green_mask_ocr(78, gy0, 375, gy1, psm=7)
            if raw:
                name = re.sub(r'[^A-Za-z0-9\s\.\-&,\'()]', '', raw).strip()
                name = re.sub(r'\s+', ' ', name)
                if not name:
                    name = "UNKNOWN"

        # ── Signature detection ──
        sig_x0 = int(w * 0.71)
        sig_x1 = int(w * 0.96)
        sig_found = False
        sig_filename = None

        if blue_start is not None and blue_end is not None and blue_end > blue_start:
            inner_x0 = sig_x0 + 4
            inner_y0 = blue_start + 4
            inner_x1 = sig_x1 - 4
            inner_y1 = blue_end - 4

            # Only check if inner box is valid
            if inner_x1 > inner_x0 and inner_y1 > inner_y0:
                inner_crop = safe_crop(img, inner_x0, inner_y0, inner_x1, inner_y1)
                inner = np.array(inner_crop.convert('L'))
                dark_px = int(np.sum(inner < 80))
                sig_found = dark_px >= 150

        # Skip if neither name nor signature
        has_name = name not in ("", "UNKNOWN")
        if not has_name and not sig_found:
            continue

        # ── Build safe filenames ──
        safe_id = re.sub(r'[^A-Za-z0-9]', '_', order_id)
        safe_name = re.sub(r'[<>:"/\\|?*]', '', name)[:40].strip()
        base_name = f"p{page_num:02d}_{safe_id} --- {safe_name}"

        # ── Save signature crop or name fallback ──
        if sig_found and blue_start is not None and blue_end is not None and blue_end > blue_start:
            sig_crop = safe_crop(img, sig_x0, blue_start, sig_x1, blue_end)
            sig_filename = f"{base_name}_signature.png"
            sig_crop.save(os.path.join(output_dir, sig_filename))
        else:
            name_crop = safe_crop(img, 78, gy0, 375, gy1)
            sig_filename = f"{base_name}_name.png"
            name_crop.save(os.path.join(output_dir, sig_filename))

        # ── Save text file ──
        txt_filename = f"{base_name}.txt"
        with open(os.path.join(output_dir, txt_filename), "w") as f:
            f.write(f"Order ID : {order_id}\n")
            f.write(f"Name     : {name}\n")
            f.write(f"Page     : {page_num}\n")
            f.write(f"Signature: {'YES' if sig_found else 'NO (name region saved)'}\n")

        orders_data.append({
            "order_id":     order_id,
            "name":         name,
            "page":         page_num,
            "sig_found":    sig_found,
            "sig_filename": sig_filename,
            "txt_filename": txt_filename,
            "job_id":       job_id,
        })

    return orders_data


# ─────────────────────────────────────────────
# RESULTS PAGE
# ─────────────────────────────────────────────

@runsheet_bp.route("/runsheet/results/<job_id>")
def runsheet_results(job_id):
    if "user" not in session:
        return redirect("/login")

    if not re.match(r'^\d+$', job_id):
        return redirect("/runsheet")

    manifest_path = os.path.join(RUNSHEET_OUTPUT_FOLDER, job_id, "manifest.json")
    if not os.path.exists(manifest_path):
        return redirect("/runsheet")

    with open(manifest_path) as f:
        data = json.load(f)

    return render_template("runsheet_results.html",
                           orders=data["orders"],
                           source=data["source"],
                           job_id=job_id)


# ─────────────────────────────────────────────
# SERVE CROPPED IMAGES
# ─────────────────────────────────────────────

@runsheet_bp.route("/runsheet/output/<job_id>/<filename>")
def runsheet_file(job_id, filename):
    if "user" not in session:
        return redirect("/login")

    if not re.match(r'^\d+$', job_id):
        return "Forbidden", 403

    folder = os.path.join(RUNSHEET_OUTPUT_FOLDER, job_id)
    return send_from_directory(folder, filename)