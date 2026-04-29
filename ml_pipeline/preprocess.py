import cv2
import numpy as np
from PIL import Image
import os

def preprocess_image(filepath):
    """
    Clean and enhance scanned document image before OCR.
    Steps: grayscale → denoise → deskew → binarize
    Returns path to processed image
    """

    img = cv2.imread(filepath)

    if img is None:
        raise ValueError(f"Could not load image from {filepath}")

    # Step 1 — Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Step 2 — Denoise
    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    # Step 3 — Deskew (straighten tilted scans)
    deskewed = deskew(denoised)

    # Step 4 — Increase contrast
    contrasted = cv2.convertScaleAbs(deskewed, alpha=1.5, beta=0)

    # Step 5 — Binarize (black and white)
    _, binary = cv2.threshold(
        contrasted, 0, 255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    # Save processed image to temp file
    processed_path = filepath.replace(".", "_processed.")
    cv2.imwrite(processed_path, binary)

    return processed_path


def deskew(image):
    """
    Straighten a tilted/rotated scanned document.
    Uses image moments to calculate skew angle.
    """
    # Find all non-zero pixels
    coords = np.column_stack(np.where(image > 0))

    if len(coords) == 0:
        return image

    # Calculate the angle
    angle = cv2.minAreaRect(coords)[-1]

    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    # Only deskew if angle is significant
    if abs(angle) < 0.5:
        return image

    # Rotate the image
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    deskewed = cv2.warpAffine(
        image, rotation_matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )

    return deskewed


def preprocess_pdf(filepath):
    """
    Convert PDF to images then preprocess each page.
    Returns list of processed image paths.
    """
    from pdf2image import convert_from_path

    pages = convert_from_path(filepath, dpi=300)
    processed_paths = []

    for i, page in enumerate(pages):
        # Save each page as image
        page_path = filepath.replace(".pdf", f"_page_{i}.png")
        page.save(page_path, "PNG")

        # Preprocess the page
        processed_path = preprocess_image(page_path)
        processed_paths.append(processed_path)

    return processed_paths


def get_preprocessed(filepath):
    """
    Main entry point — handles both images and PDFs.
    Returns list of processed image paths.
    """
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".pdf":
        return preprocess_pdf(filepath)
    else:
        return [preprocess_image(filepath)]