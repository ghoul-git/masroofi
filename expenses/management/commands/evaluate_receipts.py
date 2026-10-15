"""Evaluate the receipt pipeline (preprocess -> OCR -> LLM extraction) on a labelled dataset.

    python manage.py evaluate_receipts --dataset own
    python manage.py evaluate_receipts --dataset sroie --limit 100

Runs expenses.ai directly, not the services, so no AIUsage rows are written and no
user limits apply. Writes receipts_<dataset>_<time>.csv (one row per receipt) and
.json (summary) to --output-dir. OCR text is never written.
"""
import collections
import csv
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from expenses.evaluation import datasets, scoring
from expenses.evaluation.resources import PeakMemorySampler, Stage, machine_info, rss_mb, timestamp, write_json

STAGES = ("preprocess", "ocr", "extraction", "total")

CSV_COLUMNS = [
    "dataset", "receipt", "group", "error",
    "preprocess_s", "ocr_s", "extraction_s", "total_s",
    "rss_before_mb", "rss_after_preprocess_mb", "rss_after_ocr_mb", "rss_after_extraction_mb",
    "peak_preprocess_mb", "peak_ocr_mb", "peak_extraction_mb",
    "ocr_confidence", "input_tokens", "output_tokens",
    "label_store", "predicted_store", "store_similarity", "store_exact", "store_fuzzy",
    "label_date", "predicted_date", "date",
    "label_total", "predicted_total", "total",
    "all_correct_exact", "all_correct_fuzzy",
]


class Command(BaseCommand):
    help = "Evaluate receipt extraction accuracy, latency and memory on SROIE or the own receipts."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", choices=["sroie", "own"], required=True)
        parser.add_argument("--limit", type=int, default=None,
                            help="Number of receipts (default: 100 for sroie, all for own).")
        parser.add_argument("--output-dir", default=str(Path(settings.BASE_DIR) / "evaluation" / "results"))

    def handle(self, *args, dataset, limit, output_dir, **options):
        for name in ("OPENAI_API_KEY", "OPENAI_MODEL"):
            if not os.environ.get(name):
                raise CommandError(f"{name} is not set; the evaluation calls the real OpenAI API.")
        if dataset == "sroie" and limit is None:
            limit = 100
        receipts = datasets.load_sroie(limit) if dataset == "sroie" else datasets.load_own(limit)
        if not receipts:
            raise CommandError(f"No receipts found for dataset {dataset!r}.")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        from expenses.repositories import category_repository
        categories = category_repository.list_names()

        memory = {"baseline_mb": rss_mb()}
        # Imported here: loading EasyOCR/PyTorch is part of what is measured.
        from expenses.ai import ocr
        from expenses.ai.extraction import extract_fields
        from expenses.ai.preprocessing import preprocess
        memory["after_imports_mb"] = rss_mb()

        rows, scores, groups = [], [], collections.defaultdict(list)
        with PeakMemorySampler() as sampler:
            with Stage(sampler) as load:
                ocr.get_reader()  # load the OCR model once, before the loop
            memory.update({
                "ocr_model_load_s": load.seconds,
                "after_ocr_model_load_mb": load.rss_after,
                "ocr_model_load_peak_mb": load.peak,
            })
            self.stdout.write(f"OCR model loaded in {load.seconds:.1f} s; evaluating {len(receipts)} receipts")

            for index, receipt in enumerate(receipts, start=1):
                row, score = self._evaluate_one(receipt, dataset, sampler, preprocess, ocr.read_text,
                                                extract_fields, categories)
                rows.append(row)
                scores.append(score)
                groups[receipt["group"]].append(score)
                self.stdout.write(
                    f"[{index}/{len(receipts)}] {receipt['id']}: {row['total_s'] or 0:.1f} s, "
                    f"store {score['store_fuzzy']['outcome']}, date {score['date']['outcome']}, "
                    f"total {score['total']['outcome']}" + (f", error {row['error']}" if row["error"] else "")
                )

        name = f"receipts_{dataset}_{timestamp()}"
        with open(output_dir / f"{name}.csv", "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        write_json(output_dir / f"{name}.json", self._summary(dataset, limit, rows, scores, groups, memory))
        self.stdout.write(self.style.SUCCESS(f"Wrote {output_dir / name}.csv and .json"))

    def _evaluate_one(self, receipt, dataset, sampler, preprocess, read_text, extract_fields, categories):
        row = {"dataset": dataset, "receipt": receipt["id"], "group": receipt["group"], "error": ""}
        extracted, raw_text = {}, ""
        row["rss_before_mb"] = rss_mb()
        try:
            with Stage(sampler) as stage:
                image = preprocess(str(receipt["image_path"]))
            row.update(preprocess_s=stage.seconds, rss_after_preprocess_mb=stage.rss_after, peak_preprocess_mb=stage.peak)

            with Stage(sampler) as stage:
                raw_text, confidence = read_text(image)
            row.update(ocr_s=stage.seconds, rss_after_ocr_mb=stage.rss_after, peak_ocr_mb=stage.peak,
                       ocr_confidence=round(confidence, 4))

            if raw_text.strip():
                with Stage(sampler) as stage:
                    extracted, usage = extract_fields(raw_text, categories)
                row.update(extraction_s=stage.seconds, rss_after_extraction_mb=stage.rss_after,
                           peak_extraction_mb=stage.peak, input_tokens=usage["input_tokens"],
                           output_tokens=usage["output_tokens"])
            else:
                row["error"] = "no_text_found"
        except Exception as e:  # recorded per receipt; the run continues
            row["error"] = type(e).__name__
        finally:
            raw_text = None  # OCR text is never kept or written

        timings = [row.get(f"{s}_s") for s in ("preprocess", "ocr", "extraction")]
        row["total_s"] = sum(t for t in timings if t is not None) if any(t is not None for t in timings) else None

        score = scoring.score_receipt(extracted if isinstance(extracted, dict) else {}, receipt["label"])
        row.update({
            "label_store": scoring.redact_phone_numbers(score["store_exact"]["label"]),
            "predicted_store": scoring.redact_phone_numbers(score["store_exact"]["predicted"]),
            "store_similarity": score["store_similarity"],
            "store_exact": score["store_exact"]["outcome"],
            "store_fuzzy": score["store_fuzzy"]["outcome"],
            "label_date": score["date"]["label"],
            "predicted_date": score["date"]["predicted"],
            "date": score["date"]["outcome"],
            "label_total": score["total"]["label"],
            "predicted_total": score["total"]["predicted"],
            "total": score["total"]["outcome"],
            "all_correct_exact": score["all_correct_exact"],
            "all_correct_fuzzy": score["all_correct_fuzzy"],
        })
        for key in ("preprocess_s", "ocr_s", "extraction_s", "total_s"):
            if row.get(key) is not None:
                row[key] = round(row[key], 4)
        for key in [c for c in CSV_COLUMNS if c.endswith("_mb")]:
            if row.get(key) is not None:
                row[key] = round(row[key], 1)
        return row, score

    def _summary(self, dataset, limit, rows, scores, groups, memory):
        def column(name):
            return [r.get(name) for r in rows if r.get(name) is not None]

        return {
            "kind": "receipts",
            "dataset": dataset,
            "created_at": timestamp(),
            "limit": limit,
            "n": len(rows),
            "model": os.environ.get("OPENAI_MODEL"),
            "machine": machine_info(),
            "accuracy": {
                "overall": scoring.summarize_scores(scores),
                "groups": {group: scoring.summarize_scores(s) for group, s in groups.items()} if len(groups) > 1 else {},
            },
            "latency_s": {stage: scoring.describe(column(f"{stage}_s")) for stage in STAGES},
            "memory_mb": {
                **memory,
                "peak_per_stage": {
                    stage: scoring.describe(column(f"peak_{stage}_mb")) for stage in ("preprocess", "ocr", "extraction")
                },
            },
            "ocr_confidence": scoring.describe(column("ocr_confidence")),
            "tokens": {
                "input": scoring.describe(column("input_tokens")),
                "output": scoring.describe(column("output_tokens")),
                "total_input": sum(column("input_tokens")),
                "total_output": sum(column("output_tokens")),
            },
            "errors": dict(collections.Counter(r["error"] for r in rows if r["error"])),
        }
