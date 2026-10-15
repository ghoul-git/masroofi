"""Write evaluation/results/summary.md from the latest evaluate_receipts and evaluate_agent results.

    python manage.py evaluation_report
"""
import datetime
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from expenses.evaluation import scoring
from expenses.evaluation.resources import machine_info

FIELD_LABELS = {
    "store_exact": "Store (exact)",
    "store_fuzzy": "Store (fuzzy, similarity >= 0.8)",
    "date": "Date",
    "total": "Total",
}
STAGE_LABELS = {"preprocess": "Preprocessing (OpenCV)", "ocr": "OCR (EasyOCR)", "extraction": "Extraction (LLM)",
                "total": "Whole receipt"}
GROUP_LABELS = {"paper": "Paper photos (r01, r02)", "digital_efawateer": "Digital eFAWATEER (r03 to r08)"}


def latest(directory: Path, pattern: str):
    """The newest result file matching the pattern (file names end in a sortable timestamp)."""
    files = sorted(directory.glob(pattern))
    return (json.loads(files[-1].read_text(encoding="utf-8")), files[-1].name) if files else (None, None)


def pct(value):
    return "n/a" if value is None else f"{value * 100:.1f}%"


def sec(value):
    return "n/a" if value is None else f"{value:.2f}"


def mb(value):
    return "n/a" if value is None else f"{value:.0f}"


def tokens_count(value):
    return "n/a" if value is None else f"{value:,.0f}"


def usd(value):
    return "n/a" if value is None else f"${value:.5f}"


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


class Command(BaseCommand):
    help = "Summarize the latest evaluation results as evaluation/results/summary.md."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default=str(Path(settings.BASE_DIR) / "evaluation" / "results"))

    def handle(self, *args, output_dir, **options):
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        receipts = {}
        for dataset in ("sroie", "own"):
            data, name = latest(directory, f"receipts_{dataset}_*.json")
            if data:
                receipts[dataset] = (data, name)
        agent, agent_file = latest(directory, "agent_*.json")

        text = self._render(receipts, agent, agent_file)
        (directory / "summary.md").write_text(text, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote {directory / 'summary.md'}"))

    def _render(self, receipts, agent, agent_file):
        in_price, out_price = settings.OPENAI_INPUT_PRICE_PER_M, settings.OPENAI_OUTPUT_PRICE_PER_M
        any_run = next((d for d, _ in receipts.values()), None) or agent
        machine = (any_run or {}).get("machine") or machine_info()
        out = [
            "# Masroofi evaluation results",
            "",
            f"Generated on {datetime.date.today().isoformat()} by `python manage.py evaluation_report` "
            "from the latest result files:",
            "",
        ]
        out += [f"- {dataset}: `{name}` ({data['n']} receipts)" for dataset, (data, name) in receipts.items()]
        if agent:
            out.append(f"- agent: `{agent_file}` ({agent['n']} questions)")
        if not receipts and not agent:
            out.append("- none yet: run `evaluate_receipts` and `evaluate_agent` first")
        out += [
            "",
            "## Machine",
            "",
            table(["Item", "Value"], [
                ["Platform", machine.get("platform")],
                ["Processor", machine.get("processor")],
                ["CPU cores (physical / logical)", f"{machine.get('cpu_physical_cores')} / {machine.get('cpu_logical_cores')}"],
                ["RAM", f"{machine.get('ram_total_gb')} GB"],
                ["Python", machine.get("python")],
                ["OCR device", machine.get("ocr_device")],
                ["OpenAI model", (any_run or {}).get("model") or "n/a"],
            ]),
            "",
        ]

        # ---- accuracy
        out += ["## Extraction accuracy", "",
                "Empty prediction = miss; wrong prediction = false positive and miss. "
                "Dates are compared as YYYY-MM-DD, totals as decimals to 3 places, stores after "
                "normalizing case and spaces.", ""]
        rows = []
        for dataset, (data, _) in receipts.items():
            sections = [("All", data["accuracy"]["overall"])]
            sections += [(GROUP_LABELS.get(g, g), s) for g, s in data["accuracy"].get("groups", {}).items()]
            for group, summary in sections:
                for field, label in FIELD_LABELS.items():
                    m = summary["fields"][field]
                    rows.append([dataset, group, summary["n"], label, pct(m["accuracy"]), pct(m["precision"]),
                                 pct(m["recall"]), pct(m["f1"])])
                rows.append([dataset, group, summary["n"], "**All three correct** (exact / fuzzy store)",
                             f"{pct(summary['all_correct_exact'])} / {pct(summary['all_correct_fuzzy'])}", "", "", ""])
        out += [table(["Dataset", "Group", "n", "Field", "Accuracy", "Precision", "Recall", "F1"], rows) if rows
                else "No receipt results yet.", ""]

        # ---- latency
        out += ["## Latency (seconds)", ""]
        rows = []
        for dataset, (data, _) in receipts.items():
            rows.append([dataset, "OCR model load (once per process)", sec(data["memory_mb"]["ocr_model_load_s"]),
                         "", "", "", "", scoring.latency_class(data["memory_mb"]["ocr_model_load_s"])])
            for stage, label in STAGE_LABELS.items():
                d = data["latency_s"][stage]
                rows.append([dataset, label, sec(d["mean"]), sec(d["median"]), sec(d["p95"]), sec(d["min"]),
                             sec(d["max"]), scoring.latency_class(d["mean"])])
        if agent:
            d = agent["latency_s"]
            rows.append(["agent", "Chat question (all model calls and tools)", sec(d["mean"]), sec(d["median"]),
                         sec(d["p95"]), sec(d["min"]), sec(d["max"]), scoring.latency_class(d["mean"])])
        out += [table(["Dataset", "Operation", "Mean", "Median", "p95", "Min", "Max", "Class (by mean)"], rows) if rows
                else "No results yet.", "",
                "Classes: real-time = under 1 s, near real-time = 1 to 5 s, delayed = over 5 s.", ""]

        # ---- memory
        out += ["## Memory (process RSS, MB)", ""]
        rows = []
        for dataset, (data, _) in receipts.items():
            m = data["memory_mb"]
            rows += [
                [dataset, "Baseline (before loading the AI libraries)", mb(m["baseline_mb"])],
                [dataset, "After importing EasyOCR / PyTorch / OpenCV", mb(m["after_imports_mb"])],
                [dataset, "After loading the OCR model", mb(m["after_ocr_model_load_mb"])],
                [dataset, "Peak while loading the OCR model", mb(m["ocr_model_load_peak_mb"])],
            ]
            for stage in ("preprocess", "ocr", "extraction"):
                d = m["peak_per_stage"][stage]
                rows.append([dataset, f"Peak during {STAGE_LABELS[stage]} (median / max)", f"{mb(d['median'])} / {mb(d['max'])}"])
        if agent:
            rows.append(["agent", "Baseline", mb(agent["memory_mb"]["baseline_mb"])])
            d = agent["memory_mb"]["peak"]
            rows.append(["agent", "Peak during a question (median / max)", f"{mb(d['median'])} / {mb(d['max'])}"])
        out += [table(["Dataset", "Measurement", "RSS (MB)"], rows) if rows else "No results yet.", ""]

        # ---- agent
        out += ["## Chat agent", ""]
        if agent:
            out += [f"**Accuracy: {agent['correct']} of {agent['n']} ({pct(agent['accuracy'])})**. "
                    "Correct = every expected number appears in the answer (tolerance 0.01); "
                    "for questions it should decline, no tool was called.", ""]
            out += [table(["Question", "Expected", "Correct", "Latency (s)", "Tools"], [
                [q["question"].replace("|", "/"), q["expected_answer"], "yes" if q["correct"] else "no",
                 sec(q["latency_s"]), ", ".join(q["tools"]) or "none"]
                for q in agent["questions"]
            ]), ""]
        else:
            out += ["No agent results yet.", ""]

        # ---- cost
        out += ["## Cost (OpenAI, USD)", "",
                f"Prices: ${in_price:.2f} per million input tokens, ${out_price:.2f} per million output tokens "
                "(`OPENAI_INPUT_PRICE_PER_M`, `OPENAI_OUTPUT_PRICE_PER_M`).", ""]
        rows = []
        for dataset, (data, _) in receipts.items():
            rows.append(self._cost_row(f"{dataset}: per receipt", data["tokens"], in_price, out_price))
        if agent:
            rows.append(self._cost_row("agent: per question", agent["tokens"], in_price, out_price))
        out += [table(["Operation", "Mean input tokens", "Mean output tokens", "Mean cost", "Cost per 1,000"], rows)
                if rows else "No results yet.", ""]
        return "\n".join(out)

    def _cost_row(self, label, tokens, in_price, out_price):
        mean_in, mean_out = tokens["input"]["mean"], tokens["output"]["mean"]
        cost = scoring.cost_usd(mean_in, mean_out, in_price, out_price) if mean_in is not None else None
        return [label, tokens_count(mean_in), tokens_count(mean_out), usd(cost),
                "n/a" if cost is None else f"${cost * 1000:.2f}"]
