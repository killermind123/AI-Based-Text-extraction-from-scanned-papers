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
    "B-TOTAL.TOTAL_PRICE", "I-TOTAL.TOTAL_PRICE",
    "B-SUB_TOTAL.SUBTOTAL_PRICE", "I-SUB_TOTAL.SUBTOTAL_PRICE",
    "B-SUB_TOTAL.TAX_PRICE", "I-SUB_TOTAL.TAX_PRICE",
    "B-SUB_TOTAL.SERVICE_PRICE", "I-SUB_TOTAL.SERVICE_PRICE",
    "B-TOTAL.CASHPRICE", "I-TOTAL.CASHPRICE",
    "B-TOTAL.CHANGEPRICE", "I-TOTAL.CHANGEPRICE",
    "B-MENU.NM", "I-MENU.NM",
    "B-MENU.PRICE", "I-MENU.PRICE",
    "B-MENU.CNT", "I-MENU.CNT",
    "B-HEADER", "I-HEADER",
    "B-QUESTION", "I-QUESTION",
    "B-ANSWER", "I-ANSWER",
]

label2id = {label: i for i, label in enumerate(LABELS)}
id2label = {i: label for i, label in enumerate(LABELS)}


# ─────────────────────────────────────────────
# REGEX EXTRACTION  (runs first, highest priority)
# ─────────────────────────────────────────────

def extract_with_regex(text):
    """
    Primary extractor. Regex patterns for all target fields.
    Returns dict of { field: {"value": ..., "confidence": 0.90, "source": "regex"} }
    """
    fields = {}

    # ── ORDER ID ──────────────────────────────
    order_patterns = [
        r'(?:Order|Receipt|Invoice|Ref|No|#)[.\s#:]*([A-Z0-9\-]{4,20})',
        r'(?:Order\s*ID|Receipt\s*No|Invoice\s*No)[:\s]*([A-Z0-9\-]+)',
        r'#\s*([0-9]{4,12})',
    ]
    for pat in order_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            fields["order_id"] = {"value": m.group(1).strip(), "confidence": 0.90, "source": "regex"}
            break

    # ── DATE ──────────────────────────────────
    date_patterns = [
        r'(?:Date|Dated|Issued)[:\s]*([0-9]{1,2}[\/\-\.][0-9]{1,2}[\/\-\.][0-9]{2,4})',
        r'\b([0-9]{1,2}[\/\-\.][0-9]{1,2}[\/\-\.][0-9]{4})\b',
        r'\b([0-9]{4}[\/\-\.][0-9]{1,2}[\/\-\.][0-9]{1,2})\b',
        r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b',
    ]
    for pat in date_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            fields["date"] = {"value": m.group(1).strip(), "confidence": 0.90, "source": "regex"}
            break

    # ── TOTAL ──────────────────────────────────
    total_patterns = [
        r'(?:Grand\s+Total|Total\s+Due|Total\s+Amount|Amount\s+Due|Total)[:\s]*[$£€]?\s*([0-9,]+\.[0-9]{2})',
        r'(?:Total)[^\n$£€0-9]*[$£€]?\s*([0-9,]+\.[0-9]{2})',
        r'TOTAL[^\n]*?([0-9]+\.[0-9]{2})',
    ]
    for pat in total_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            fields["total"] = {"value": m.group(1).strip().replace(',', ''), "confidence": 0.90, "source": "regex"}
            break

    # ── SUBTOTAL ───────────────────────────────
    m = re.search(
        r'(?:Sub\s*Total|Subtotal)[:\s]*[$£€]?\s*([0-9,]+\.[0-9]{2})',
        text, re.IGNORECASE
    )
    if m:
        fields["subtotal"] = {"value": m.group(1).strip().replace(',', ''), "confidence": 0.90, "source": "regex"}

    # ── TAX ────────────────────────────────────
    m = re.search(
        r'(?:Tax|VAT|GST|HST)[:\s]*[$£€]?\s*([0-9,]+\.[0-9]{2})',
        text, re.IGNORECASE
    )
    if m:
        fields["tax"] = {"value": m.group(1).strip().replace(',', ''), "confidence": 0.90, "source": "regex"}

    # ── NAME ───────────────────────────────────
    name_patterns = [
        r'(?:Name|Customer|Client|Bill\s*To|Sold\s*To)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
        r'(?:Served\s*by|Cashier|Staff)[:\s]+([A-Za-z\s]+)',
    ]
    for pat in name_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if len(val) > 2:
                fields["name"] = {"value": val, "confidence": 0.85, "source": "regex"}
                break

    # ── ADDRESS ────────────────────────────────
    address_patterns = [
        r'(\d+\s+[\w\s]{2,30}(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Boulevard|Blvd|Way|Close|Crescent)[.,]?\s*[\w\s,]{0,40})',
        r'(?:Address|Location)[:\s]+(.{10,80}?)(?:\n|Tel|Phone|Email|$)',
    ]
    for pat in address_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip().replace('\n', ', ')
            if len(val) > 5:
                fields["address"] = {"value": val, "confidence": 0.85, "source": "regex"}
                break

    # ── SIGNATURE ──────────────────────────────
    # Signatures are hard to extract from text — flag presence from keyword
    sig_match = re.search(
        r'(?:Signature|Signed|Authorised\s*By|Authorized\s*By)[:\s]*([A-Za-z\s\.]{2,40})',
        text, re.IGNORECASE
    )
    if sig_match:
        val = sig_match.group(1).strip()
        if len(val) > 1:
            fields["signature"] = {"value": val, "confidence": 0.80, "source": "regex"}

    # ── PHONE ──────────────────────────────────
    m = re.search(
        r'(?:Tel|Phone|Contact)[:\s]*([+\d\s\-()]{7,20})',
        text, re.IGNORECASE
    )
    if m:
        fields["phone"] = {"value": m.group(1).strip(), "confidence": 0.85, "source": "regex"}

    # ── EMAIL ──────────────────────────────────
    m = re.search(r'[\w.\-+]+@[\w\-]+\.[a-zA-Z]{2,}', text)
    if m:
        fields["email"] = {"value": m.group(0).strip(), "confidence": 0.95, "source": "regex"}

    return fields


# ─────────────────────────────────────────────
# MODEL LOADING
# ─────────────────────────────────────────────

def load_model(model_path=None):
    if model_path and os.path.exists(model_path):
        print(f"Loading fine-tuned model from {model_path}")
        processor = LayoutLMv3Processor.from_pretrained(model_path, apply_ocr=False)
        model = LayoutLMv3ForTokenClassification.from_pretrained(model_path)
        global label2id, id2label
        label2id = model.config.label2id
        id2label = model.config.id2label
    else:
        print("Fine-tuned model not found — loading base model...")
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


# ─────────────────────────────────────────────
# MODEL-BASED EXTRACTION  (fallback / supplement)
# ─────────────────────────────────────────────

def normalize_boxes(boxes, image_width, image_height):
    normalized = []
    for box in boxes:
        normalized.append([
            max(0, min(1000, int(1000 * box[0] / image_width))),
            max(0, min(1000, int(1000 * box[1] / image_height))),
            max(0, min(1000, int(1000 * box[2] / image_width))),
            max(0, min(1000, int(1000 * box[3] / image_height))),
        ])
    return normalized


def extract_with_model(image_path, ocr_result, processor, model):
    """Run LayoutLMv3 model and return raw extracted fields."""
    image = Image.open(image_path).convert("RGB")
    width, height = image.size

    words = ocr_result.get("words", [])
    boxes = ocr_result.get("boxes", [])

    if not words:
        return {}

    norm_boxes = normalize_boxes(boxes, width, height)

    encoding = processor(
        image, words,
        boxes=norm_boxes,
        return_tensors="pt",
        truncation=True,
        padding="max_length",
        max_length=512
    )

    with torch.no_grad():
        outputs = model(**encoding)

    predictions = outputs.logits.argmax(-1).squeeze().tolist()
    probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1).squeeze()
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

        if word_id >= len(words):
            continue
        word = words[word_id]

        if label.startswith("B-"):
            if current_field and current_words:
                extracted[current_field.lower()] = {
                    "value": " ".join(current_words),
                    "confidence": sum(current_confs) / len(current_confs),
                    "source": "model"
                }
            current_field = label[2:]
            current_words = [word]
            current_confs = [confidence]

        elif label.startswith("I-") and current_field:
            current_words.append(word)
            current_confs.append(confidence)

        else:
            if current_field and current_words:
                extracted[current_field.lower()] = {
                    "value": " ".join(current_words),
                    "confidence": sum(current_confs) / len(current_confs),
                    "source": "model"
                }
            current_field = None
            current_words = []
            current_confs = []

    if current_field and current_words:
        extracted[current_field.lower()] = {
            "value": " ".join(current_words),
            "confidence": sum(current_confs) / len(current_confs),
            "source": "model"
        }

    return extracted


# ─────────────────────────────────────────────
# MAIN ENTRY POINT — regex first, model fills gaps
# ─────────────────────────────────────────────

def extract_fields(image_path, ocr_result, processor, model):
    """
    Primary extraction pipeline:
      1. Run regex on raw OCR text  (fast, deterministic, high confidence)
      2. Run LayoutLMv3 model       (fills any fields regex missed)
      3. Merge: regex result wins when both found a field
    """
    raw_text = ocr_result.get("raw_text", "")

    # Step 1 — regex
    regex_fields = extract_with_regex(raw_text)

    # Step 2 — model (only if processor/model provided)
    model_fields = {}
    if processor is not None and model is not None:
        try:
            model_fields = extract_with_model(image_path, ocr_result, processor, model)
        except Exception as e:
            print(f"[Model extraction failed, regex only] {e}")

    # Step 3 — merge: regex wins, model fills gaps
    merged = {**model_fields, **regex_fields}

    return merged


# ─────────────────────────────────────────────
# LEGACY ALIAS (keeps existing route code working)
# ─────────────────────────────────────────────

def extract_fields_simple(ocr_result):
    """Regex-only extraction (no model). Used for quick testing."""
    text = ocr_result.get("raw_text", "")
    return extract_with_regex(text)