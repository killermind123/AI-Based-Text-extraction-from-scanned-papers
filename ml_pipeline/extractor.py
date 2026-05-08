from transformers import (
    LayoutLMv3Processor,
    LayoutLMv3ForTokenClassification
)
import torch
from PIL import Image
import os
import re

LABELS = [
    "O",
    "B-TOTAL", "I-TOTAL",
    "B-DATE", "I-DATE",
    "B-ADDRESS", "I-ADDRESS",
    "B-ORDER_ID", "I-ORDER_ID",
    "B-INVOICE", "I-INVOICE",
    "B-SIGNATURE", "I-SIGNATURE",
]

label2id = {label: i for i, label in enumerate(LABELS)}
id2label = {i: label for i, label in enumerate(LABELS)}


def load_model(model_path=None):
    """
    Load LayoutLMv3 model and processor.
    """
    if model_path and os.path.exists(model_path):
        print(f"Loading fine-tuned model from {model_path}")
        processor = LayoutLMv3Processor.from_pretrained(
            model_path,
            apply_ocr=False
        )
        model = LayoutLMv3ForTokenClassification.from_pretrained(
            model_path
        )
    else:
        print("Fine-tuned model not found, loading base model...")
        processor = LayoutLMv3Processor.from_pretrained(
            "microsoft/layoutlmv3-base",
            apply_ocr=False
        )
        model = LayoutLMv3ForTokenClassification.from_pretrained(
            "microsoft/layoutlmv3-base",
            num_labels=len(LABELS),
            id2label=id2label,
            label2id=label2id,
            ignore_mismatched_sizes=True
        )

    model.eval()
    return processor, model


def normalize_boxes(boxes, image_width, image_height):
    """Normalize bounding boxes to 0-1000 scale."""
    normalized = []
    for box in boxes:
        normalized.append([
            max(0, min(1000, int(1000 * box[0] / image_width))),
            max(0, min(1000, int(1000 * box[1] / image_height))),
            max(0, min(1000, int(1000 * box[2] / image_width))),
            max(0, min(1000, int(1000 * box[3] / image_height))),
        ])
    return normalized


def extract_fields(image_path, ocr_result, processor, model):
    """
    Main LayoutLMv3 extraction function.
    Takes image path and OCR result, returns extracted fields.
    """
    image = Image.open(image_path).convert("RGB")
    width, height = image.size

    words = ocr_result["words"]
    boxes = ocr_result["boxes"]

    if not words:
        return {}

    norm_boxes = normalize_boxes(boxes, width, height)

    encoding = processor(
        image,
        words,
        boxes=norm_boxes,
        return_tensors="pt",
        truncation=True,
        padding="max_length",
        max_length=512
    )

    with torch.no_grad():
        outputs = model(**encoding)

    predictions = outputs.logits.argmax(-1).squeeze().tolist()
    probabilities = torch.nn.functional.softmax(
        outputs.logits, dim=-1
    ).squeeze()

    word_ids = encoding.word_ids(0)

    extracted = {}
    current_field = None
    current_words = []
    current_confs = []

    for idx, (pred, word_id) in enumerate(zip(predictions, word_ids)):
        if word_id is None:
            continue

        label = id2label.get(pred, "O")
        confidence = float(probabilities[idx][pred])

        if word_id < len(words):
            word = words[word_id]
        else:
            continue

        if label.startswith("B-"):
            if current_field and current_words:
                field_key = current_field.lower()
                extracted[field_key] = {
                    "value": " ".join(current_words),
                    "confidence": sum(current_confs) / len(current_confs)
                }
            current_field = label[2:]
            current_words = [word]
            current_confs = [confidence]

        elif label.startswith("I-") and current_field:
            current_words.append(word)
            current_confs.append(confidence)

        else:
            if current_field and current_words:
                field_key = current_field.lower()
                extracted[field_key] = {
                    "value": " ".join(current_words),
                    "confidence": sum(current_confs) / len(current_confs)
                }
            current_field = None
            current_words = []
            current_confs = []

    if current_field and current_words:
        field_key = current_field.lower()
        extracted[field_key] = {
            "value": " ".join(current_words),
            "confidence": sum(current_confs) / len(current_confs)
        }

    return extracted


def extract_fields_simple(ocr_result):
    """
    Regex fallback extraction.
    Used as baseline comparison in dissertation.
    """
    text = ocr_result.get("raw_text", "")
    fields = {}

    # Total
    total_match = re.search(
        r'Total[^$\n]*\$([0-9,]+\.?[0-9]*)',
        text, re.IGNORECASE
    )
    if total_match:
        fields["total"] = {
            "value": total_match.group(1).strip(),
            "confidence": 0.75
        }

    # Date
    date_match = re.search(
        r'(?:date)[:\s]*([0-9]{1,2}[-\/][0-9]{1,2}[-\/][0-9]{2,4})',
        text, re.IGNORECASE
    )
    if date_match:
        fields["date"] = {
            "value": date_match.group(1).strip(),
            "confidence": 0.75
        }

    # Receipt number
    receipt_match = re.search(
        r'Receipt\s*#?\s*([0-9]+)',
        text, re.IGNORECASE
    )
    if receipt_match:
        fields["order_id"] = {
            "value": receipt_match.group(1).strip(),
            "confidence": 0.75
        }

    # Address
    address_match = re.search(
        r'(\d+\s+\w+\s+(?:St|Street|Ave|Avenue|Rd|Road|Blvd)[.,\s]+\w+)',
        text, re.IGNORECASE
    )
    if address_match:
        fields["address"] = {
            "value": address_match.group(1).strip(),
            "confidence": 0.75
        }

    return fields