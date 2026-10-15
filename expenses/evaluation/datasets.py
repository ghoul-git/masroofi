"""Loaders for the two receipt datasets. Each returns a list of
{"id", "image_path", "group", "label": {"store_name", "date", "total"}}.
"""
import csv
import json
from pathlib import Path

from django.conf import settings

EVALUATION_DIR = Path(settings.BASE_DIR) / "evaluation"

# SROIE 2019, test split only:
#   test/img/<id>.jpg       the receipt photo
#   test/entities/<id>.txt  JSON labels: {"company", "date", "address", "total"}
#   test/box/<id>.txt       OCR boxes "x1,y1,...,x4,y4,text" (not used)
SROIE_TEST_DIR = EVALUATION_DIR / "sroie" / "SROIE2019" / "test"

# Own receipts: evaluation/receipts/ with labels.csv (file,store_name,date,total).
OWN_DIR = EVALUATION_DIR / "receipts"
OWN_GROUPS = {
    "paper": ["r01", "r02"],
    "digital_efawateer": ["r03", "r04", "r05", "r06", "r07", "r08"],
}


def load_sroie(limit=None, directory=SROIE_TEST_DIR) -> list[dict]:
    """The first `limit` SROIE test receipts, in file-name order. "company" is the store; "address" is ignored."""
    directory = Path(directory)
    receipts = []
    for entity_file in sorted((directory / "entities").glob("*.txt")):
        image = directory / "img" / f"{entity_file.stem}.jpg"
        if not image.exists():
            continue
        data = json.loads(entity_file.read_text(encoding="utf-8-sig"))
        receipts.append({
            "id": entity_file.stem,
            "image_path": image,
            "group": "sroie_test",
            "label": {"store_name": data.get("company", ""), "date": data.get("date", ""), "total": data.get("total", "")},
        })
        if limit and len(receipts) >= limit:
            break
    return receipts


def own_group(file_name: str) -> str:
    stem = Path(file_name).stem
    return next((group for group, stems in OWN_GROUPS.items() if stem in stems), "other")


def load_own(limit=None, directory=OWN_DIR) -> list[dict]:
    """Receipts listed in labels.csv, in file order."""
    directory = Path(directory)
    with open(directory / "labels.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    receipts = []
    for row in rows:
        receipts.append({
            "id": Path(row["file"]).stem,
            "image_path": directory / row["file"],
            "group": own_group(row["file"]),
            "label": {"store_name": row["store_name"], "date": row["date"], "total": row["total"]},
        })
        if limit and len(receipts) >= limit:
            break
    return receipts


def load_questions(path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{"question": r["question"], "expected_answer": r["expected_answer"]} for r in csv.DictReader(f)]
