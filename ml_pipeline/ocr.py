import pytesseract
import cv2
import os

# Windows Tesseract path
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\S22247228\Downloads\tesseract.exe"


def extract_text(image_path, method="tesseract"):
    """
    OCR using Tesseract.
    Returns words, bounding boxes and confidences.
    """
    img = cv2.imread(image_path)

    if img is None:
        raise ValueError(f"Could not load image: {image_path}")

    height, width = img.shape[:2]
    config = r'--oem 3 --psm 6'

    # Get detailed OCR data including bounding boxes
    data = pytesseract.image_to_data(
        img,
        config=config,
        output_type=pytesseract.Output.DICT
    )

    words = []
    boxes = []
    confidences = []

    for i, word in enumerate(data['text']):
        # Skip empty words
        if word.strip() == '':
            continue

        conf = float(data['conf'][i])

        # Skip very low confidence
        if conf < 0:
            continue

        x = data['left'][i]
        y = data['top'][i]
        w = data['width'][i]
        h = data['height'][i]

        # Only add if box has valid dimensions
        if w > 0 and h > 0:
            words.append(word)
            boxes.append([x, y, x + w, y + h])
            confidences.append(conf / 100.0)

    print(f"OCR found {len(words)} words with {len(boxes)} boxes")

    return {
        "words": words,
        "boxes": boxes,
        "confidences": confidences,
        "raw_text": " ".join(words),
        "image_width": width,
        "image_height": height
    }


def normalize_boxes(boxes, image_width, image_height):
    """
    Normalize bounding boxes to 0-1000 scale for LayoutLMv3.
    """
    normalized = []
    for box in boxes:
        normalized.append([
            max(0, min(1000, int(1000 * box[0] / image_width))),
            max(0, min(1000, int(1000 * box[1] / image_height))),
            max(0, min(1000, int(1000 * box[2] / image_width))),
            max(0, min(1000, int(1000 * box[3] / image_height))),
        ])
    return normalized