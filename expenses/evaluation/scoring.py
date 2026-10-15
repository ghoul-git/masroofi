"""Scoring for the evaluation commands. Pure functions: no database, OCR or OpenAI.

Field scoring (store, date, total), per field over a set of receipts:
- correct prediction            -> true positive
- empty prediction              -> miss (false negative)
- wrong prediction              -> false positive and miss
- prediction with no label      -> false positive
precision = TP / (TP + FP), recall = TP / (TP + FN), F1 = harmonic mean,
accuracy = share of receipts where the field is right (including "nothing to find, nothing found").
"""
import datetime
import math
import re
import statistics
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from difflib import SequenceMatcher

FUZZY_THRESHOLD = 0.8
TOTAL_PLACES = Decimal("0.001")

MONTHS = {
    name: number
    for number, names in enumerate(
        [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",),
         ("jun", "june"), ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"),
         ("oct", "october"), ("nov", "november"), ("dec", "december")],
        start=1,
    )
    for name in names
}

# Arabic-Indic and Eastern Arabic-Indic digits, and the Arabic decimal and thousands separators.
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")


# ---------------------------------------------------------------- normalization


def _year(text: str) -> int:
    year = int(text)
    return year + 2000 if year < 100 else year


def _make_date(year, month, day):
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def normalize_date(value) -> str | None:
    """Any common receipt date format -> "YYYY-MM-DD", or None.

    Day/month/year is tried first (Jordan and Malaysia, where SROIE comes from);
    month/day/year is used only when day/month is impossible, e.g. 4/22/2018.
    Two-digit years are 20YY. Month names may be short or full: 22 MAR 18, 27/Mar/2018.
    """
    if value is None:
        return None
    text = str(value).strip().translate(_ARABIC_DIGITS)
    if not text:
        return None

    # Year first: 2018-03-27, 2018/03/27, 2018.03.27
    m = re.fullmatch(r"(\d{4})[-/. ](\d{1,2})[-/. ](\d{1,2})", text)
    if m:
        date = _make_date(int(m[1]), int(m[2]), int(m[3]))
        return date.isoformat() if date else None

    # Day, month name, year: 22 MAR 18, 27/MAR/2018, 28-Feb-2018
    m = re.fullmatch(r"(\d{1,2})[-/. ]*([A-Za-z]+)[-/., ]*(\d{2}|\d{4})", text)
    if m:
        month = MONTHS.get(m[2].lower())
        date = month and _make_date(_year(m[3]), month, int(m[1]))
        return date.isoformat() if date else None

    # Numbers only: 15/01/2019, 20-11-17, 23.03.18, 1/8/2018, 4/22/2018
    m = re.fullmatch(r"(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{2}|\d{4})", text)
    if m:
        first, second, year = int(m[1]), int(m[2]), _year(m[3])
        date = _make_date(year, second, first) or _make_date(year, first, second)
        return date.isoformat() if date else None
    return None


def normalize_total(value) -> Decimal | None:
    """"RM 12.50", "$1,230.79", "12.5", 12.345 -> Decimal to 3 places, or None.

    A comma is a thousands separator when followed by exactly 3 digits (1,230.79 or 1,230),
    otherwise a decimal comma (12,50).
    """
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().translate(_ARABIC_DIGITS)
    text = re.sub(r"[^\d.,\-]", "", text)
    if not re.search(r"\d", text):
        return None
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", "") if re.search(r",\d{3}$", text) else text.replace(",", ".")
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return number.quantize(TOTAL_PLACES, rounding=ROUND_HALF_UP)


def normalize_store(value) -> str:
    """Case-insensitive, with runs of whitespace collapsed to one space."""
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def store_similarity(predicted, label) -> float:
    a, b = normalize_store(predicted), normalize_store(label)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------- one receipt


def score_receipt(predicted: dict, label: dict) -> dict:
    """Compare one receipt's predicted store/date/total with its labels.

    Each field gets: "label", "predicted" (normalized), and "outcome", one of
    "correct", "wrong", "missing" (empty prediction), "no_label" or "extra" (prediction with no label).
    Store is scored twice: store_exact and store_fuzzy (similarity >= FUZZY_THRESHOLD).
    """
    pred_store, label_store = normalize_store(predicted.get("store_name")), normalize_store(label.get("store_name"))
    similarity = store_similarity(pred_store, label_store)
    pred_date, label_date = normalize_date(predicted.get("date")), normalize_date(label.get("date"))
    pred_total, label_total = normalize_total(predicted.get("total")), normalize_total(label.get("total"))

    fields = {
        "store_exact": (pred_store, label_store, pred_store == label_store),
        "store_fuzzy": (pred_store, label_store, similarity >= FUZZY_THRESHOLD),
        "date": (pred_date, label_date, pred_date == label_date),
        "total": (pred_total, label_total, pred_total == label_total),
    }
    scored = {}
    for name, (pred, lab, same) in fields.items():
        has_pred, has_label = pred not in (None, ""), lab not in (None, "")
        if not has_label:
            outcome = "extra" if has_pred else "no_label"
        elif not has_pred:
            outcome = "missing"
        else:
            outcome = "correct" if same else "wrong"
        scored[name] = {
            "label": None if lab is None else str(lab),
            "predicted": None if pred is None else str(pred),
            "outcome": outcome,
        }
    scored["store_similarity"] = round(similarity, 4)
    scored["all_correct_exact"] = all(scored[f]["outcome"] in ("correct", "no_label") for f in ("store_exact", "date", "total"))
    scored["all_correct_fuzzy"] = all(scored[f]["outcome"] in ("correct", "no_label") for f in ("store_fuzzy", "date", "total"))
    return scored


# ---------------------------------------------------------------- many receipts

FIELDS = ("store_exact", "store_fuzzy", "date", "total")


def field_metrics(outcomes: list[str]) -> dict:
    """Accuracy, precision, recall and F1 from a list of score_receipt outcomes for one field."""
    tp = outcomes.count("correct")
    wrong = outcomes.count("wrong")
    fp = wrong + outcomes.count("extra")
    fn = wrong + outcomes.count("missing")
    right = tp + outcomes.count("no_label")
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "n": len(outcomes),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "accuracy": right / len(outcomes) if outcomes else 0.0,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def summarize_scores(scores: list[dict]) -> dict:
    """Per-field metrics and the share of receipts with store, date and total all correct."""
    n = len(scores)
    return {
        "n": n,
        "fields": {field: field_metrics([s[field]["outcome"] for s in scores]) for field in FIELDS},
        "all_correct_exact": sum(s["all_correct_exact"] for s in scores) / n if n else 0.0,
        "all_correct_fuzzy": sum(s["all_correct_fuzzy"] for s in scores) / n if n else 0.0,
    }


# ---------------------------------------------------------------- chat answers


def numbers_in(text) -> list[Decimal]:
    """Every number in a text, after removing thousands separators: "1,230.79 JOD" -> [1230.79].

    Arabic-Indic digits and separators (٦٣٫٧١٠) are converted first.
    """
    text = str(text or "").translate(_ARABIC_DIGITS)
    text = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", text)
    return [Decimal(n) for n in re.findall(r"-?\d+(?:\.\d+)?", text)]


def answer_is_correct(answer, expected_answer, tools_used, tolerance=Decimal("0.01")) -> bool:
    """For "decline": correct if no tool was called. Otherwise every number in the expected
    answer must appear in the answer, within the tolerance."""
    if str(expected_answer).strip().lower() == "decline":
        return not tools_used
    expected = numbers_in(expected_answer)
    found = numbers_in(answer)
    return bool(expected) and all(any(abs(e - f) <= tolerance for f in found) for e in expected)


# ---------------------------------------------------------------- statistics and reporting


def percentile(values, pct) -> float | None:
    """Linear-interpolation percentile (like numpy's default); None for no values."""
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    rank = (len(values) - 1) * pct / 100
    low, high = math.floor(rank), math.ceil(rank)
    return float(values[low] + (values[high] - values[low]) * (rank - low))


def describe(values) -> dict:
    """mean, median, p95, min, max (None when there are no values)."""
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0, "mean": None, "median": None, "p95": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p95": percentile(values, 95),
        "min": min(values),
        "max": max(values),
    }


def latency_class(seconds) -> str:
    """real-time (under 1 s), near real-time (1 to 5 s) or delayed (over 5 s)."""
    if seconds is None:
        return "n/a"
    if seconds < 1:
        return "real-time"
    if seconds <= 5:
        return "near real-time"
    return "delayed"


def cost_usd(input_tokens, output_tokens, input_price_per_m, output_price_per_m) -> float:
    return (input_tokens or 0) * input_price_per_m / 1_000_000 + (output_tokens or 0) * output_price_per_m / 1_000_000


_PHONE = re.compile(r"(?:\+|\b00)?\d[\d\s\-()./]{6,}\d")


def redact_phone_numbers(text) -> str:
    """Replace anything that looks like a phone number (7+ digits with separators) before writing results.

    Only for free text such as store names: dates and amounts can also have 7+ digits.
    """
    if text is None:
        return ""

    def replace(match):
        digits = re.sub(r"\D", "", match.group())
        return "[number removed]" if len(digits) >= 7 else match.group()

    return _PHONE.sub(replace, str(text))
