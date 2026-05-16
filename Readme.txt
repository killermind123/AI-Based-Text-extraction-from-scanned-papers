# AI-Based Text Extraction from Scanned Documents

A web-based application that automates the extraction of key information from scanned documents using OCR and a fine-tuned LayoutLMv3 model. Built as a final year dissertation project for ABC Logistics, which collects proof of deliveries via paper runsheets when handheld scanners fail.

---

## Project Overview

When delivery scanners break, drivers collect signatures on paper runsheets. These must be manually processed to extract delivery information. This system automates that process by:

- Accepting scanned documents (PNG, JPG, PDF, TIFF)
- Preprocessing images (deskew, denoise, binarize)
- Running Tesseract OCR to extract words and bounding boxes
- Using a fine-tuned LayoutLMv3 model to identify and label key fields
- Falling back to regex extraction when the model is uncertain
- Saving results to a cloud database (Supabase/PostgreSQL)
- Displaying extracted fields with confidence scores via a web dashboard

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python Flask |
| Frontend | HTML/CSS (Jinja2 templates) |
| Database | PostgreSQL (Supabase) / SQLite (local fallback) |
| OCR | Tesseract |
| AI Model | LayoutLMv3 (Microsoft) fine-tuned on CORD + FUNSD |
| Image Processing | OpenCV |
| Deep Learning | PyTorch + HuggingFace Transformers |

---

## Prerequisites

### 1. Python
Python 3.10 or higher is required.
Download from https://www.python.org/downloads/

### 2. Tesseract OCR (required — must install separately)

Tesseract is not installable via pip. Install it as a system binary:

**Windows:**
- Download the installer from https://github.com/UB-Mannheim/tesseract/wiki
- During installation, tick **"Add Tesseract to system PATH"**
- Restart your terminal after installation

**Linux:**
```bash
sudo apt install tesseract-ocr
```

**Mac:**
```bash
brew install tesseract
```

After installation, verify it works:
```bash
tesseract --version
```

### 3. Poppler (required for PDF support only)

**Windows:**
- Download from https://github.com/oschwartz10612/poppler-windows/releases
- Extract and add the `bin/` folder to your system PATH

**Linux:**
```bash
sudo apt install poppler-utils
```

**Mac:**
```bash
brew install poppler
```

---

## Installation

### Step 1 — Clone the repository
```bash
git clone <your-repo-url>
cd AI-Based-Text-extraction-from-scanned-papers
```

### Step 2 — Create a virtual environment
```bash
python -m venv venv
```

Activate it:

**Windows:**
```bash
venv\Scripts\activate
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

### Step 3 — Install PyTorch (CPU version)
```bash
pip install torch==2.11.0+cpu torchvision==0.26.0+cpu --index-url https://download.pytorch.org/whl/cpu
```

### Step 4 — Install remaining dependencies
```bash
pip install -r requirements.txt
```

---

## Configuration

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql://postgres.<project-id>:<password>@aws-0-eu-west-1.pooler.supabase.com:5432/postgres
SECRET_KEY=your-secret-key-here
```

**Notes:**
- If `DATABASE_URL` is not set or Supabase is unreachable, the app will automatically fall back to SQLite (`database.db`)
- Supabase requires an IPv6-capable network (eduroam works; some wired university networks do not)
- The `SECRET_KEY` can be any random string — it is used to sign session cookies

---

## Running the Application

```bash
python app.py
```

Then open your browser and go to:
```
http://127.0.0.1:5000
```

---

## Project Structure

```
AI-Based-Text-extraction/
├── routes/
│   ├── auth.py
│   ├── dashboard.py
│   ├── login.py
│   ├── logout.py
│   ├── signup.py
│   ├── upload.py           ← main document upload pipeline
│   └── runsheet.py         ← logistics runsheet extractor
├── ml_pipeline/
│   ├── __init__.py
│   ├── preprocess.py       ← OpenCV image cleaning
│   ├── ocr.py              ← Tesseract OCR
│   ├── extractor.py        ← LayoutLMv3 inference + regex fallback
│   ├── postprocess.py      ← field cleaning and validation
│   └── models/
│       └── layoutlmv3-finetuned/   ← fine-tuned model weights
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── signup.html
│   ├── dashboard.html
│   ├── upload.html
│   ├── uploaded.html
│   ├── profile.html
│   ├── runsheet_upload.html
│   └── runsheet_results.html
├── static/
│   └── style.css
├── uploads/                ← uploaded documents (auto-created)
├── runsheet_outputs/       ← runsheet extraction results (auto-created)
├── app.py                  ← Flask entry point
├── database.py             ← database connection and schema
├── requirements.txt
├── .env                    ← environment variables (not committed)
└── README.md
```

---

## Features

### Document Upload & Extraction
- Upload PNG, JPG, PDF, or TIFF files
- Automatic image preprocessing (grayscale, denoise, deskew, binarize)
- Tesseract OCR extracts words and bounding boxes
- LayoutLMv3 model identifies and labels key fields
- Regex fallback ensures reliable extraction when model confidence is low
- Confidence scores displayed per field

### Runsheet Extractor
- Dedicated page at `/runsheet` for logistics paper runsheets
- Automatically detects each order block on the page
- Extracts Order ID and Company Name via OCR
- Detects and crops signature regions
- Falls back to name region if no signature is present
- Results page shows all extracted orders with image previews and download buttons

### User Authentication
- Secure signup and login with hashed passwords
- Session-based authentication

### Dashboard
- Overview of all uploaded documents
- Processing status, field count, and upload history

### Profile
- Edit username and email
- Change password
- Document history with status badges

---

## AI Model Details

| Property | Value |
|---|---|
| Base model | microsoft/layoutlmv3-base |
| Training datasets | CORD v2 (800 receipts) + FUNSD (149 forms) |
| Training environment | Google Colab T4 GPU |
| Epochs | 5 |
| Batch size | 4 |
| Learning rate | 1e-5 |
| Best F1 score | 0.963 |

### Labels Used
```
O, B-TOTAL.TOTAL_PRICE, I-TOTAL.TOTAL_PRICE,
B-SUB_TOTAL.SUBTOTAL_PRICE, I-SUB_TOTAL.SUBTOTAL_PRICE,
B-SUB_TOTAL.TAX_PRICE, I-SUB_TOTAL.TAX_PRICE,
B-SUB_TOTAL.SERVICE_PRICE, I-SUB_TOTAL.SERVICE_PRICE,
B-TOTAL.CASHPRICE, I-TOTAL.CASHPRICE,
B-TOTAL.CHANGEPRICE, I-TOTAL.CHANGEPRICE,
B-MENU.NM, I-MENU.NM, B-MENU.PRICE, I-MENU.PRICE,
B-MENU.CNT, I-MENU.CNT,
B-HEADER, I-HEADER, B-QUESTION, I-QUESTION, B-ANSWER, I-ANSWER
```

---

## Known Limitations

1. **Domain mismatch** — LayoutLMv3 was trained on CORD receipts and FUNSD forms, not logistics delivery documents. The regex extractor handles domain-specific fields more reliably.

2. **Tesseract dependency** — Tesseract must be installed as a system binary. PaddleOCR was considered as an alternative but is incompatible with Python 3.14.

3. **Network dependency for Supabase** — Supabase uses IPv6 by default. On IPv4-only networks the app falls back to local SQLite automatically.

4. **No real runsheet training data** — The runsheet extractor uses computer vision and OCR rather than a trained model, due to the absence of annotated logistics document datasets.

---

## Future Work

- Fine-tune LayoutLMv3 on annotated logistics runsheet data
- YOLO-based order box detection on runsheets
- Export extracted results to CSV/JSON
- React frontend replacement
- Comparison dashboard (Tesseract vs LayoutLMv3 accuracy)
- Signature verification using image similarity

---

## Author

Student ID: S22247228
Module: Final Year Dissertation
Institution: Birmingham City University
