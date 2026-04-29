import pytesseract
import cv2
import numpy as np
from PIL import Image
import os

# Tesseract path — Windows
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\S22247228\Downloads\tesseract.exe"

def extract_text_tesseract(image_path):
    """
    Baseline OCR using Tesseract.
    Used for dissertation comparison.
    Returns raw text string.
    """
    img = cv2.imread(image_path)
    config = r'--oem 3 --psm 6'
    text = pytesseract.image_to_string(img, config=config)
    return text.strip()


def extract_text_paddle(image_path):
    """
    Improved OCR using PaddleOCR.
    Returns list of (word, bbox, confidence) tuples.
    """
    try:
        from paddleocr import PaddleOCR

        ocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
        result = ocr.ocr(image_path, cls=True)

        words = []
        boxes = []
        confidences = []

        for line in result[0]:
            box = line[0]        # bounding box [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
            word = line[1][0]    # text
            conf = line[1][1]    # confidence score

            # Convert box to [x_min, y_min, x_max, y_max]
            x_coords = [p[0] for p in box]
            y_coords = [p[1] for p in box]
            bbox = [min(x_coords), min(y_coords),
                    max(x_coords), max(y_coords)]

            words.append(word)
            boxes.append(bbox)
            confidences.append(conf)

        return {
            "words": words,
            "boxes": boxes,
            "confidences": confidences,
            "raw_text": " ".join(words)
        }

    except ImportError:
        print("PaddleOCR not installed — falling back to Tesseract")
        text = extract_text_tesseract(image_path)
        return {
            "words": text.split(),
            "boxes": [],
            "confidences": [],
            "raw_text": text
        }


def extract_text(image_path, method="paddle"):
    """
    Main entry point for OCR.
    method: 'paddle' (default) or 'tesseract' (baseline)
    """
    if method == "tesseract":
        text = extract_text_tesseract(image_path)
        return {
            "words": text.split(),
            "boxes": [],
            "confidences": [],
            "raw_text": text
        }
    else:
        return extract_text_paddle(image_path)


def normalize_boxes(boxes, image_width, image_height):
    """
    Normalize bounding boxes to 0-1000 scale for LayoutLMv3.
    """
    normalized = []
    for box in boxes:
        normalized.append([
            int(1000 * box[0] / image_width),
            int(1000 * box[1] / image_height),
            int(1000 * box[2] / image_width),
            int(1000 * box[3] / image_height),
        ])
    return normalized