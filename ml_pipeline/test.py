import torch
from transformers import (
    LayoutLMv3Processor,
    LayoutLMv3ForTokenClassification,
    TrainingArguments,
    Trainer
)
from datasets import load_dataset
from torch.utils.data import Dataset
import numpy as np
from seqeval.metrics import f1_score, precision_score, recall_score
import os

# ===================================
# Label definitions
# Must match extractor.py exactly
# ===================================
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

# ===================================
# CORD label mapping
# Maps CORD dataset labels to ours
# ===================================
CORD_TO_OURS = {
    "total.total_price": "TOTAL",
    "total.subtotal_price": "TOTAL",
    "sub_total.subtotal_price": "TOTAL",
    "menu.price": "TOTAL",
    "total.tax_price": "TOTAL",
    "void_menu.price": "TOTAL",
    "total.discount_price": "TOTAL",
    "total.emoneyprice": "TOTAL",
    "total.changeprice": "TOTAL",
    "total.creditcardprice": "TOTAL",
    "total.cashprice": "TOTAL",
    "total.menutype_cnt": "TOTAL",
    "total.menuqty_cnt": "TOTAL",
}


class CORDDataset(Dataset):
    """
    PyTorch Dataset for CORD receipt data.
    Prepares images, words, boxes and labels
    for LayoutLMv3 training.
    """

    def __init__(self, dataset, processor, max_length=512):
        self.dataset = dataset
        self.processor = processor
        self.max_length = max_length

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, idx):
        item = self.dataset[idx]

        image = item["image"].convert("RGB")
        words = []
        boxes = []
        word_labels = []

        width, height = image.size

        # Extract words, boxes and labels from CORD format
        for field in item["ground_truth"]["gt_parse"].get("menu", []):
            for key, value in field.items():
                if isinstance(value, str) and value.strip():
                    words.append(value)
                    # Use dummy box if not available
                    boxes.append([0, 0, width, height])
                    word_labels.append("O")

        # Handle empty documents
        if not words:
            words = ["empty"]
            boxes = [[0, 0, 100, 100]]
            word_labels = ["O"]

        # Normalize boxes
        norm_boxes = []
        for box in boxes:
            norm_boxes.append([
                int(1000 * box[0] / width),
                int(1000 * box[1] / height),
                int(1000 * box[2] / width),
                int(1000 * box[3] / height),
            ])

        # Convert labels to IDs
        label_ids = [label2id.get(l, 0) for l in word_labels]

        # Encode for LayoutLMv3
        encoding = self.processor(
            image,
            words,
            boxes=norm_boxes,
            word_labels=label_ids,
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt"
        )

        # Squeeze batch dimension
        return {
            "input_ids": encoding["input_ids"].squeeze(),
            "attention_mask": encoding["attention_mask"].squeeze(),
            "bbox": encoding["bbox"].squeeze(),
            "pixel_values": encoding["pixel_values"].squeeze(),
            "labels": encoding["labels"].squeeze(),
        }


def compute_metrics(eval_pred):
    """
    Compute F1, precision and recall scores.
    These go in your dissertation evaluation chapter!
    """
    predictions, labels = eval_pred
    predictions = np.argmax(predictions, axis=2)

    true_predictions = [
        [id2label[p] for p, l in zip(prediction, label) if l != -100]
        for prediction, label in zip(predictions, labels)
    ]

    true_labels = [
        [id2label[l] for p, l in zip(prediction, label) if l != -100]
        for prediction, label in zip(predictions, labels)
    ]

    return {
        "precision": precision_score(true_labels, true_predictions),
        "recall": recall_score(true_labels, true_predictions),
        "f1": f1_score(true_labels, true_predictions),
    }


def train():
    """
    Main training function.
    Run this file directly to start training.
    """

    print("Loading CORD dataset...")
    dataset = load_dataset("naver-clova-ix/cord-v2")

    train_data = dataset["train"]
    val_data = dataset["validation"]

    print(f"Train samples: {len(train_data)}")
    print(f"Validation samples: {len(val_data)}")

    print("Loading LayoutLMv3 processor...")
    processor = LayoutLMv3Processor.from_pretrained(
        "microsoft/layoutlmv3-base",
        apply_ocr=False
    )

    print("Loading LayoutLMv3 model...")
    model = LayoutLMv3ForTokenClassification.from_pretrained(
        "microsoft/layoutlmv3-base",
        num_labels=len(LABELS),
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True
    )

    print("Preparing datasets...")
    train_dataset = CORDDataset(train_data, processor)
    val_dataset = CORDDataset(val_data, processor)

    # ===================================
    # Training configuration
    # ===================================
    training_args = TrainingArguments(
        output_dir="ml_pipeline/models/layoutlmv3-finetuned",
        num_train_epochs=5,
        per_device_train_batch_size=2,
        per_device_eval_batch_size=2,
        learning_rate=1e-5,
        weight_decay=0.01,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        logging_dir="ml_pipeline/models/logs",
        logging_steps=50,
        save_total_limit=2,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        tokenizer=processor,
        compute_metrics=compute_metrics,
    )

    print("Starting training...")
    print("This will take a while on CPU — go make a cup of tea!")
    trainer.train()

    print("Saving fine-tuned model...")
    model_save_path = "ml_pipeline/models/layoutlmv3-finetuned"
    trainer.save_model(model_save_path)
    processor.save_pretrained(model_save_path)

    print(f"Model saved to {model_save_path}")
    print("Training complete!")


if __name__ == "__main__":
    train()