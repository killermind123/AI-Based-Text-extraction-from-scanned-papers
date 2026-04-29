from transformers import (
    LayoutLMv3Processor,
    LayoutLMv3ForTokenClassification,
    AutoProcessor
)
import torch
from PIL import Image
import os

# ===================================
# Label definitions for receipts
# Based on CORD dataset structure
# ===================================
LABELS = [
    "O",              # Outside — not a field
    "B-TOTAL",        # Beginning of total amount
    "I-TOTAL",        # Inside total amount
    "B-DATE",         # Beginning of date
    "I-DATE",         # Inside date
    "B-ADDRESS",      # Beginning of address
    "I-ADDRESS",      # Inside address
    "B-ORDER_ID",     # Beginning of order ID
    "I-ORDER_ID",     # Inside order ID
    "B-INVOICE",      # Beginning of invoice number
    "I-INVOICE",      # Inside invoice number
    "B-SIGNATURE",    # Beginning of signature
    "I-SIGNATURE",    # Inside signature
]

# Map label to ID and back
label2id = {label: i for i, label in enumerate(LABELS)}
id2label = {i: label for i, label in enumerate(LABELS)}


def load_model(model_path=None):
    """
    Load LayoutLMv3 model and processor.
    If model_path is None, loads base pretrained model.
    If model_path is given, loads your fine-tuned model.
    """
    if model_path and os.path.exists(model_path):
        print(f"Loading fine-tuned model from {model_path}")
        processor = LayoutLMv3Processor.from_pretrained(model_path)
        model = LayoutLMv3ForTokenClassification.from_pretrained(model_path)
    else:
        print("Loading base LayoutLMv3 model from HuggingFace...")
        processor = LayoutLMv3Processor.from_pretrained(
            "microsoft/layoutlmv3-base",
            apply_ocr=False  # We do OCR ourselves with Tesseract
        )
        model = LayoutLMv3ForTokenClassification.from_pretrained(
            "microsoft/layoutlmv3-base",
            num_labels=len(LABELS),
            id2label=id2label,
            label2id=label2id,
            ignore_mismatched_sizes=True
        )

    model.eval()  # Set to evaluation mode
    return processor, model


def normalize_boxes(boxes, image_width, image_height):
    """
    Normalize bounding boxes to 0-1000 scale.
    LayoutLMv3 requires this specific scale.
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


def extract_fields(image_path, ocr_result, processor, model):
    """
    Main extraction function.
    
    Takes:
        image_path  — path to the scanned document image
        ocr_result  — dict from ocr.py with words, boxes, confidences
        processor   — LayoutLMv3 processor
        model       — LayoutLMv3 model
    
    Returns:
        dict of field_name → {value, confidence}
    """

    # Load image
    image = Image.open(image_path).convert("RGB")
    width, height = image.size

    words = ocr_result["words"]
    boxes = ocr_result["boxes"]

    if not words:
        return {}

    # Normalize boxes to 0-1000 scale
    norm_boxes = normalize_boxes(boxes, width, height)

    # Encode inputs for LayoutLMv3
    encoding = processor(
        image,
        words,
        boxes=norm_boxes,
        return_tensors="pt",
        truncation=True,
        padding="max_length",
        max_length=512
    )

    # Run model inference
    with torch.no_grad():
        outputs = model(**encoding)

    # Get predicted label for each token
    predictions = outputs.logits.argmax(-1).squeeze().tolist()
    probabilities = torch.nn.functional.softmax(
        outputs.logits, dim=-1
    ).squeeze()

    # Decode token IDs back to words
    token_boxes = encoding.bbox.squeeze().tolist()
    tokens = encoding.input_ids.squeeze().tolist()
    word_ids = encoding.word_ids(0)

    # ===================================
    # Group predictions into fields
    # ===================================
    extracted = {}
    current_field = None
    current_words = []
    current_confs = []

    for idx, (pred, word_id) in enumerate(zip(predictions, word_ids)):
        if word_id is None:
            continue

        label = id2label.get(pred, "O")
        confidence = float(probabilities[idx][pred])

        # Get the actual word
        if word_id < len(words):
            word = words[word_id]
        else:
            continue

        if label.startswith("B-"):
            # Save previous field if exists
            if current_field and current_words:
                field_key = current_field.lower()
                extracted[field_key] = {
                    "value": " ".join(current_words),
                    "confidence": sum(current_confs) / len(current_confs)
                }

            # Start new field
            current_field = label[2:]  # Remove "B-"
            current_words = [word]
            current_confs = [confidence]

        elif label.startswith("I-") and current_field:
            # Continue current field
            current_words.append(word)
            current_confs.append(confidence)

        else:
            # Outside — save current field if exists
            if current_field and current_words:
                field_key = current_field.lower()
                extracted[field_key] = {
                    "value": " ".join(current_words),
                    "confidence": sum(current_confs) / len(current_confs)
                }
            current_field = None
            current_words = []
            current_confs = []

    # Save last field if exists
    if current_field and current_words:
        field_key = current_field.lower()
        extracted[field_key] = {
            "value": " ".join(current_words),
            "confidence": sum(current_confs) / len(current_confs)
        }

    return extracted


def extract_fields_simple(ocr_result):
    """
    Fallback extraction using regex when LayoutLMv3 
    is not yet fine-tuned.
    Used as baseline in dissertation comparison.
    """
    import re
    text = ocr_result.get("raw_text", "")
    fields = {}

    patterns = {
        "total": r'Total[:\s]*\$?([0-9,.]+)',
        "date": r'Date[:\s]*([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4})',
        "order_id": r'Order\s*ID[:\s]*([A-Z0-9\-]+)',
        "invoice": r'Invoice\s*(Number|No\.?)?[:\s]*([A-Z0-9\-]+)',
        "address": r'Address[:\s]*([\s\S]{10,200}?)(?=\n\n|\Z)',
    }

    for field, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(2) if field == "invoice" else match.group(1)
            fields[field] = {
                "value": value.strip(),
                "confidence": 0.75  # Fixed baseline confidence
            }

    return fields