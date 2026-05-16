import cv2
import numpy as np
import os

def preprocess_image(filepath):
    """
    Clean image before OCR.
    Uses adaptive thresholding for better results on clean receipts.
    """
    img = cv2.imread(filepath)

    if img is None:
        raise ValueError(f"Could not load image from {filepath}")

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Denoise
    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    # Deskew
    deskewed = deskew(denoised)

    # Use adaptive threshold instead of global
    # Works much better for receipts with varying lighting
    binary = cv2.adaptiveThreshold(
        deskewed,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,
        2
    )

    # Save processed image
    processed_path = filepath.replace(".", "_processed.")
    cv2.imwrite(processed_path, binary)

    return processed_path


def deskew(image):
    """Straighten tilted scanned documents."""
    coords = np.column_stack(np.where(image > 0))

    if len(coords) == 0:
        return image

    angle = cv2.minAreaRect(coords)[-1]

    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    if abs(angle) < 0.5:
        return image

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
    """Convert PDF pages to images then preprocess."""
    from pdf2image import convert_from_path
    pages = convert_from_path(filepath, dpi=300)
    processed_paths = []

    for i, page in enumerate(pages):
        page_path = filepath.replace(".pdf", f"_page_{i}.png")
        page.save(page_path, "PNG")
        processed_path = preprocess_image(page_path)
        processed_paths.append(processed_path)

    return processed_paths


def get_preprocessed(filepath):
    """
    For clean digital receipts — skip aggressive preprocessing.
    Only preprocess if image is actually poor quality.
    """
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".pdf":
        return preprocess_pdf(filepath)

    # Check image quality first
    img = cv2.imread(filepath)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Calculate blur score — higher = sharper
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    print(f"Image blur score: {blur_score}")

    # If image is already sharp and clean — skip preprocessing
    if blur_score > 100:
        print("Clean image detected — skipping preprocessing")
        return [filepath]  # Use original file directly
    else:
        print("Poor quality image — applying preprocessing")
        return [preprocess_image(filepath)]