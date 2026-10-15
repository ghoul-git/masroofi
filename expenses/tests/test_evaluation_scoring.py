"""Scoring functions of the evaluation commands. No OpenAI, EasyOCR or database."""
from decimal import Decimal

from django.test import SimpleTestCase

from expenses.evaluation import scoring
from expenses.evaluation.datasets import own_group


class NormalizeDateTests(SimpleTestCase):
    def test_sroie_formats(self):
        cases = {
            "15/01/2019": "2019-01-15",
            "22-03-2018": "2018-03-22",
            "03/03/18": "2018-03-03",
            "20-11-17": "2017-11-20",
            "23.03.18": "2018-03-23",
            "07 MAR 2018": "2018-03-07",
            "22 MAR 18": "2018-03-22",
            "27/MAR/2018": "2018-03-27",
            "28-FEB-2018": "2018-02-28",
            "1/8/2018": "2018-08-01",
            "23/2/2018": "2018-02-23",
            "2018/03/27": "2018-03-27",
            "2016-07-31": "2016-07-31",
            "5 October 2026": "2026-10-05",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(scoring.normalize_date(raw), expected)

    def test_day_month_first_and_month_day_only_when_impossible(self):
        self.assertEqual(scoring.normalize_date("05/10/2026"), "2026-10-05")  # 5 October, not 10 May
        self.assertEqual(scoring.normalize_date("4/22/2018"), "2018-04-22")  # 22 cannot be a month

    def test_arabic_digits(self):
        self.assertEqual(scoring.normalize_date("٠٥/١٠/٢٠٢٦"), "2026-10-05")

    def test_invalid_or_empty(self):
        for raw in [None, "", "  ", "yesterday", "31/02/2024", "2024-13-01", "99/99/99", "15 FOO 2019"]:
            with self.subTest(raw=raw):
                self.assertIsNone(scoring.normalize_date(raw))


class NormalizeTotalTests(SimpleTestCase):
    def test_formats(self):
        cases = {
            "193.00": "193.000",
            "RM 9.00": "9.000",
            "RM12.50": "12.500",
            "$1,230.79": "1230.790",
            "1,230": "1230.000",
            "12,50": "12.500",
            "61.2": "61.200",
            "-9.99": "-9.990",
            12.345: "12.345",
            "12.3455": "12.346",
            "٦٣٫٧١٠": "63.710",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(scoring.normalize_total(raw), Decimal(expected))

    def test_invalid_or_empty(self):
        for raw in [None, "", "RM", "abc", True]:
            with self.subTest(raw=raw):
                self.assertIsNone(scoring.normalize_total(raw))


class StoreTests(SimpleTestCase):
    def test_normalize_case_and_spaces(self):
        self.assertEqual(scoring.normalize_store("  OJC   Marketing\tSDN BHD "), "ojc marketing sdn bhd")

    def test_similarity(self):
        self.assertEqual(scoring.store_similarity("Orange Jordan", "ORANGE  JORDAN"), 1.0)
        self.assertGreaterEqual(scoring.store_similarity("OJC MARKETING SDN BHD", "OJC MARKETING SDN. BHD."), 0.8)
        self.assertLess(scoring.store_similarity("Carrefour", "Cozmo"), 0.8)
        self.assertEqual(scoring.store_similarity("", "Cozmo"), 0.0)


LABEL = {"store_name": "OJC MARKETING SDN BHD", "date": "15/01/2019", "total": "RM 193.00"}


class ScoreReceiptTests(SimpleTestCase):
    def test_all_correct(self):
        s = scoring.score_receipt({"store_name": "ojc marketing sdn bhd", "date": "2019-01-15", "total": 193}, LABEL)
        self.assertEqual({f: s[f]["outcome"] for f in scoring.FIELDS},
                         {"store_exact": "correct", "store_fuzzy": "correct", "date": "correct", "total": "correct"})
        self.assertTrue(s["all_correct_exact"])
        self.assertTrue(s["all_correct_fuzzy"])
        self.assertEqual(s["date"]["predicted"], "2019-01-15")
        self.assertEqual(s["total"]["label"], "193.000")

    def test_fuzzy_store_only(self):
        s = scoring.score_receipt({"store_name": "OJC MARKETING SDN. BHD.", "date": "15/01/2019", "total": "193"}, LABEL)
        self.assertEqual(s["store_exact"]["outcome"], "wrong")
        self.assertEqual(s["store_fuzzy"]["outcome"], "correct")
        self.assertFalse(s["all_correct_exact"])
        self.assertTrue(s["all_correct_fuzzy"])

    def test_wrong_and_missing(self):
        s = scoring.score_receipt({"store_name": "", "date": "2019-01-16", "total": None}, LABEL)
        self.assertEqual(s["store_exact"]["outcome"], "missing")
        self.assertEqual(s["date"]["outcome"], "wrong")
        self.assertEqual(s["total"]["outcome"], "missing")
        self.assertFalse(s["all_correct_fuzzy"])

    def test_total_compared_to_3_places(self):
        label = {**LABEL, "total": "25.000"}
        self.assertEqual(scoring.score_receipt({"total": "25.0004"}, label)["total"]["outcome"], "correct")
        self.assertEqual(scoring.score_receipt({"total": "25.001"}, label)["total"]["outcome"], "wrong")

    def test_unparseable_prediction_counts_as_missing(self):
        self.assertEqual(scoring.score_receipt({"date": "not a date"}, LABEL)["date"]["outcome"], "missing")

    def test_prediction_without_label(self):
        s = scoring.score_receipt({"date": "2019-01-15"}, {"store_name": "X", "date": "", "total": "1"})
        self.assertEqual(s["date"]["outcome"], "extra")
        s = scoring.score_receipt({}, {"store_name": "X", "date": "", "total": "1"})
        self.assertEqual(s["date"]["outcome"], "no_label")


class FieldMetricsTests(SimpleTestCase):
    def test_counts_and_rates(self):
        # 6 correct, 2 wrong (FP + FN each), 1 missing (FN), 1 extra (FP)
        m = scoring.field_metrics(["correct"] * 6 + ["wrong"] * 2 + ["missing", "extra"])
        self.assertEqual((m["n"], m["tp"], m["fp"], m["fn"]), (10, 6, 3, 3))
        self.assertAlmostEqual(m["accuracy"], 0.6)
        self.assertAlmostEqual(m["precision"], 6 / 9)
        self.assertAlmostEqual(m["recall"], 6 / 9)
        self.assertAlmostEqual(m["f1"], 6 / 9)

    def test_empty_predictions_lower_recall_not_precision(self):
        m = scoring.field_metrics(["correct", "correct", "missing", "missing"])
        self.assertEqual(m["precision"], 1.0)
        self.assertEqual(m["recall"], 0.5)
        self.assertAlmostEqual(m["f1"], 2 / 3)
        self.assertEqual(m["accuracy"], 0.5)

    def test_no_label_and_nothing_predicted_counts_as_right(self):
        self.assertEqual(scoring.field_metrics(["no_label", "correct"])["accuracy"], 1.0)

    def test_no_outcomes(self):
        m = scoring.field_metrics([])
        self.assertEqual((m["accuracy"], m["precision"], m["recall"], m["f1"]), (0.0, 0.0, 0.0, 0.0))

    def test_summary_share_all_correct(self):
        good = scoring.score_receipt({"store_name": LABEL["store_name"], "date": "2019-01-15", "total": "193"}, LABEL)
        fuzzy = scoring.score_receipt({"store_name": "OJC MARKETING SDN. BHD.", "date": "2019-01-15", "total": "193"}, LABEL)
        bad = scoring.score_receipt({}, LABEL)
        summary = scoring.summarize_scores([good, fuzzy, bad, good])
        self.assertEqual(summary["n"], 4)
        self.assertEqual(summary["all_correct_exact"], 0.5)
        self.assertEqual(summary["all_correct_fuzzy"], 0.75)
        self.assertEqual(summary["fields"]["date"]["tp"], 3)
        self.assertEqual(summary["fields"]["date"]["fn"], 1)


class AnswerScoringTests(SimpleTestCase):
    def test_numbers_in_text(self):
        self.assertEqual(scoring.numbers_in("You spent 1,230.79 JOD and 63.71 JOD."), [Decimal("1230.79"), Decimal("63.71")])
        self.assertEqual(scoring.numbers_in("1,234,567.5"), [Decimal("1234567.5")])
        self.assertEqual(scoring.numbers_in("صرفت ٦٣٫٧١٠ دينار"), [Decimal("63.710")])
        self.assertEqual(scoring.numbers_in("1,2"), [Decimal("1"), Decimal("2")])  # not a thousands separator

    def test_every_expected_number_must_appear_within_tolerance(self):
        self.assertTrue(scoring.answer_is_correct("You spent 63.71 JOD.", "63.710", ["get_spending_total"]))
        self.assertTrue(scoring.answer_is_correct("1,230.79 in September vs 63.715 in October", "1230.790 63.710", ["x"]))
        self.assertTrue(scoring.answer_is_correct("about 61.21 JOD", "61.200", ["x"]))
        self.assertFalse(scoring.answer_is_correct("about 61.22 JOD", "61.200", ["x"]))
        self.assertFalse(scoring.answer_is_correct("September was 1,230.79", "1230.790 63.710", ["x"]))
        self.assertFalse(scoring.answer_is_correct("", "15.500", ["x"]))

    def test_decline_means_no_tool_called(self):
        self.assertTrue(scoring.answer_is_correct("I can only help with your expenses.", "decline", []))
        self.assertTrue(scoring.answer_is_correct("Sorry.", " Decline ", []))
        self.assertFalse(scoring.answer_is_correct("It is sunny.", "decline", [{"name": "list_expenses"}]))


class StatisticsTests(SimpleTestCase):
    def test_percentile_and_describe(self):
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertAlmostEqual(scoring.percentile(values, 95), 9.55)
        self.assertEqual(scoring.percentile([4.2], 95), 4.2)
        self.assertIsNone(scoring.percentile([], 95))
        d = scoring.describe([3, 1, 2, None])
        self.assertEqual((d["n"], d["mean"], d["median"], d["min"], d["max"]), (3, 2, 2, 1, 3))
        self.assertEqual(scoring.describe([])["mean"], None)

    def test_latency_class(self):
        self.assertEqual(scoring.latency_class(0.4), "real-time")
        self.assertEqual(scoring.latency_class(1.0), "near real-time")
        self.assertEqual(scoring.latency_class(5.0), "near real-time")
        self.assertEqual(scoring.latency_class(5.01), "delayed")
        self.assertEqual(scoring.latency_class(None), "n/a")

    def test_cost(self):
        self.assertAlmostEqual(scoring.cost_usd(1_000_000, 200_000, 0.10, 0.50), 0.20)
        self.assertEqual(scoring.cost_usd(None, None, 0.10, 0.50), 0.0)


class PrivacyAndGroupTests(SimpleTestCase):
    def test_phone_numbers_are_removed(self):
        self.assertEqual(scoring.redact_phone_numbers("Cozmo Tel: 06 581 2345"), "Cozmo Tel: [number removed]")
        self.assertEqual(scoring.redact_phone_numbers("Shop +962 79 123 4567"), "Shop [number removed]")
        self.assertEqual(scoring.redact_phone_numbers("Orange Jordan"), "Orange Jordan")
        self.assertEqual(scoring.redact_phone_numbers("7-Eleven 24"), "7-Eleven 24")
        self.assertEqual(scoring.redact_phone_numbers(None), "")

    def test_own_groups(self):
        self.assertEqual(own_group("r01.jpg"), "paper")
        self.assertEqual(own_group("r02.jpg"), "paper")
        for name in ["r03.jpeg", "r05.jpeg", "r08.jpeg"]:
            self.assertEqual(own_group(name), "digital_efawateer")
        self.assertEqual(own_group("r09.jpg"), "other")

    def test_scoring_module_does_not_import_the_ai_code(self):
        import inspect
        import re
        imports = re.findall(r"^\s*(?:from|import)\s+(\S+)", inspect.getsource(scoring), re.MULTILINE)
        for name in imports:
            self.assertFalse(name.startswith(("expenses.ai", "openai", "easyocr", "cv2", "torch")), name)
