"""Evaluate the chat agent on a list of questions with known answers.

    python manage.py evaluate_agent --username demo

Asks each question through expenses.ai.agent.answer for that user with an empty
history (no AIUsage rows, no limits) and writes agent_<time>.csv and .json.
An answer is correct when every number in expected_answer appears in it
(thousands separators removed, tolerance 0.01); for "decline", when no tool was
called. The manual_check column is left empty for a person to fill in.
"""
import collections
import csv
import json
import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from expenses.evaluation import datasets, scoring
from expenses.evaluation.resources import PeakMemorySampler, Stage, machine_info, rss_mb, timestamp, write_json

CSV_COLUMNS = [
    "question", "expected_answer", "answer", "tools_used", "correct", "manual_check", "error",
    "latency_s", "input_tokens", "output_tokens", "rss_before_mb", "rss_after_mb", "peak_mb",
]


class Command(BaseCommand):
    help = "Evaluate the chat agent's answers, latency, tokens and memory."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True, help="The user whose expenses the questions are about.")
        parser.add_argument("--questions", default=str(Path(settings.BASE_DIR) / "evaluation" / "chat_questions.csv"))
        parser.add_argument("--output-dir", default=str(Path(settings.BASE_DIR) / "evaluation" / "results"))

    def handle(self, *args, username, questions, output_dir, **options):
        for name in ("OPENAI_API_KEY", "OPENAI_MODEL"):
            if not os.environ.get(name):
                raise CommandError(f"{name} is not set; the evaluation calls the real OpenAI API.")
        user = get_user_model().objects.filter(username=username).first()
        if user is None:
            raise CommandError(f"No user named {username!r}.")
        items = datasets.load_questions(questions)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        from expenses.ai import agent

        baseline = rss_mb()
        rows = []
        with PeakMemorySampler() as sampler:
            for index, item in enumerate(items, start=1):
                row = {"question": item["question"], "expected_answer": item["expected_answer"],
                       "manual_check": "", "error": "", "answer": "", "tools_used": "[]"}
                tools = []
                try:
                    with Stage(sampler) as stage:
                        result = agent.answer(user, item["question"], [])
                    tools = result["tools_used"]
                    row.update(
                        answer=result["answer"],
                        tools_used=json.dumps(tools, ensure_ascii=False),
                        input_tokens=result.get("usage", {}).get("input_tokens", 0),
                        output_tokens=result.get("usage", {}).get("output_tokens", 0),
                    )
                except Exception as e:  # recorded per question; the run continues
                    row["error"] = type(e).__name__
                    stage = None
                if stage is not None:
                    row.update(latency_s=round(stage.seconds, 4), rss_before_mb=round(stage.rss_before, 1),
                               rss_after_mb=round(stage.rss_after, 1), peak_mb=round(stage.peak, 1))
                row["correct"] = not row["error"] and scoring.answer_is_correct(
                    row["answer"], item["expected_answer"], tools)
                rows.append(row)
                # Question text can be Arabic; print only the number so any console can show it.
                self.stdout.write(f"[{index}/{len(items)}] {row.get('latency_s', 0) or 0:.1f} s, "
                                  f"{'correct' if row['correct'] else 'WRONG'}, {len(tools)} tool call(s)"
                                  + (f", error {row['error']}" if row["error"] else ""))

        name = f"agent_{timestamp()}"
        with open(output_dir / f"{name}.csv", "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

        def column(key):
            return [r[key] for r in rows if r.get(key) is not None]

        correct = sum(bool(r["correct"]) for r in rows)
        write_json(output_dir / f"{name}.json", {
            "kind": "agent",
            "created_at": timestamp(),
            "n": len(rows),
            "correct": correct,
            "accuracy": correct / len(rows) if rows else 0.0,
            "model": os.environ.get("OPENAI_MODEL"),
            "machine": machine_info(),
            "latency_s": scoring.describe(column("latency_s")),
            "tokens": {
                "input": scoring.describe(column("input_tokens")),
                "output": scoring.describe(column("output_tokens")),
                "total_input": sum(column("input_tokens")),
                "total_output": sum(column("output_tokens")),
            },
            "memory_mb": {"baseline_mb": baseline, "peak": scoring.describe(column("peak_mb"))},
            "questions": [
                {"question": r["question"], "expected_answer": r["expected_answer"], "correct": bool(r["correct"]),
                 "latency_s": r.get("latency_s"), "tools": [t["name"] for t in json.loads(r["tools_used"])],
                 "error": r["error"]}
                for r in rows
            ],
            "errors": dict(collections.Counter(r["error"] for r in rows if r["error"])),
        })
        self.stdout.write(self.style.SUCCESS(f"{correct}/{len(rows)} correct. Wrote {output_dir / name}.csv and .json"))
