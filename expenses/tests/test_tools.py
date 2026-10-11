import json

from django.test import TestCase

from expenses.ai import tools
from expenses.ai.tools import TOOL_SCHEMAS, run_tool
from expenses.tests.factories import make_category, make_expense, make_user

SEPTEMBER = {"start_date": "2026-09-01", "end_date": "2026-09-30"}
OCTOBER = {"start_date": "2026-10-01", "end_date": "2026-10-31"}


class ToolFixtureMixin:
    """Alice has expenses in September and October; Bob has larger ones in the same dates."""

    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        food = make_category("food")
        transport = make_category("transport")
        make_category("bills")

        # Alice, September: food 20.00, transport 5.00
        make_expense(self.alice, food, "Carrefour", "20.00", date="2026-09-10")
        make_expense(self.alice, transport, "Careem", "5.00", date="2026-09-15")
        # Alice, October: food 12.50 + 7.25 + 30.00 (USD), transport 4.00
        make_expense(self.alice, food, "Carrefour", "12.50", date="2026-10-02")
        make_expense(self.alice, food, "Cozmo", "7.25", date="2026-10-20")
        make_expense(self.alice, transport, "Careem", "4.00", date="2026-10-31")
        make_expense(self.alice, food, "Amazon", "30.00", date="2026-10-05", currency="USD")
        # Outside both periods
        make_expense(self.alice, food, "Carrefour", "99.00", date="2026-11-01")

        # Bob, same dates, store names that must never show up for Alice
        make_expense(self.bob, food, "Bob Market", "500.00", date="2026-10-03")
        make_expense(self.bob, transport, "Bob Taxi", "300.00", date="2026-09-12")
        make_expense(self.bob, food, "Bob Market", "70.00", date="2026-10-04", currency="USD")


class ToolTotalsTests(ToolFixtureMixin, TestCase):
    def test_get_spending_total(self):
        result = run_tool(self.alice, "get_spending_total", {**OCTOBER, "category": None})
        self.assertEqual(result["totals"], [
            {"currency": "USD", "total": "30.00", "count": 1},
            {"currency": "JOD", "total": "23.75", "count": 3},
        ])
        self.assertEqual(result["expense_count"], 4)

    def test_get_spending_total_for_one_category_ignores_case(self):
        result = run_tool(self.alice, "get_spending_total", {**SEPTEMBER, "category": "FOOD"})
        self.assertEqual(result["category"], "Food")
        self.assertEqual(result["totals"], [{"currency": "JOD", "total": "20.00", "count": 1}])

    def test_get_spending_total_with_no_expenses(self):
        result = run_tool(self.alice, "get_spending_total", {"start_date": "2025-01-01", "end_date": "2025-01-31"})
        self.assertEqual(result["totals"], [])
        self.assertEqual(result["expense_count"], 0)

    def test_dates_are_inclusive(self):
        result = run_tool(self.alice, "get_spending_total", {"start_date": "2026-10-31", "end_date": "2026-10-31"})
        self.assertEqual(result["totals"], [{"currency": "JOD", "total": "4.00", "count": 1}])

    def test_get_spending_by_category(self):
        result = run_tool(self.alice, "get_spending_by_category", OCTOBER)
        self.assertEqual(result["categories"], [
            {"category": "Food", "currency": "USD", "total": "30.00", "count": 1},
            {"category": "Food", "currency": "JOD", "total": "19.75", "count": 2},
            {"category": "Transport", "currency": "JOD", "total": "4.00", "count": 1},
        ])

    def test_list_expenses(self):
        result = run_tool(self.alice, "list_expenses", {**OCTOBER, "category": None, "store": None, "limit": None})
        self.assertEqual(result["total_matching"], 4)
        self.assertEqual([e["date"] for e in result["expenses"]], ["2026-10-31", "2026-10-20", "2026-10-05", "2026-10-02"])
        self.assertEqual(result["expenses"][0], {
            "id": result["expenses"][0]["id"],
            "date": "2026-10-31",
            "store_name": "Careem",
            "category": "Transport",
            "total": "4.00",
            "currency": "JOD",
        })

    def test_list_expenses_filters_by_store_and_category_and_limit(self):
        result = run_tool(self.alice, "list_expenses", {"start_date": "2026-09-01", "end_date": "2026-11-30", "store": "carre"})
        self.assertEqual(result["total_matching"], 3)
        self.assertTrue(all(e["store_name"] == "Carrefour" for e in result["expenses"]))

        result = run_tool(self.alice, "list_expenses", {**OCTOBER, "category": "food", "limit": 2})
        self.assertEqual(result["total_matching"], 3)
        self.assertEqual(len(result["expenses"]), 2)

    def test_get_top_expenses(self):
        result = run_tool(self.alice, "get_top_expenses", {**OCTOBER, "limit": 2})
        self.assertEqual([(e["store_name"], e["total"]) for e in result["expenses"]], [
            ("Amazon", "30.00"),
            ("Carrefour", "12.50"),
        ])

    def test_get_top_expenses_default_limit_is_5(self):
        result = run_tool(self.alice, "get_top_expenses", {"start_date": "2026-01-01", "end_date": "2026-12-31", "limit": None})
        self.assertEqual(len(result["expenses"]), 5)
        self.assertEqual(result["expenses"][0]["total"], "99.00")

    def test_compare_periods(self):
        result = run_tool(self.alice, "compare_periods", {
            "first_start": "2026-09-01", "first_end": "2026-09-30",
            "second_start": "2026-10-01", "second_end": "2026-10-31",
            "category": None,
        })
        self.assertEqual(result["comparison"], [
            {"currency": "JOD", "first_total": "25.00", "second_total": "23.75", "change": "-1.25", "change_percent": -5.0},
            {"currency": "USD", "first_total": "0.00", "second_total": "30.00", "change": "30.00", "change_percent": None},
        ])

    def test_compare_periods_for_one_category(self):
        result = run_tool(self.alice, "compare_periods", {
            "first_start": "2026-09-01", "first_end": "2026-09-30",
            "second_start": "2026-10-01", "second_end": "2026-10-31",
            "category": "transport",
        })
        self.assertEqual(result["comparison"], [
            {"currency": "JOD", "first_total": "5.00", "second_total": "4.00", "change": "-1.00", "change_percent": -20.0},
        ])

    def test_results_are_json_serializable(self):
        for name, arguments in [
            ("get_spending_total", OCTOBER),
            ("get_spending_by_category", OCTOBER),
            ("list_expenses", OCTOBER),
            ("get_top_expenses", OCTOBER),
            ("compare_periods", {"first_start": "2026-09-01", "first_end": "2026-09-30",
                                 "second_start": "2026-10-01", "second_end": "2026-10-31"}),
        ]:
            with self.subTest(tool=name):
                json.dumps(run_tool(self.alice, name, arguments))


class ToolIsolationTests(ToolFixtureMixin, TestCase):
    """Bob's expenses share dates, categories and currencies with Alice's, so any leak changes the numbers."""

    WIDE = {"start_date": "2026-01-01", "end_date": "2026-12-31"}

    def assert_no_bob_stores(self, result):
        # Only the returned expenses are checked: a "store" filter of "Bob" is echoed back in the result.
        self.assertNotIn("Bob", json.dumps(result["expenses"]))

    def test_totals_never_include_another_user(self):
        result = run_tool(self.alice, "get_spending_total", self.WIDE)
        self.assertEqual(result["totals"], [
            {"currency": "JOD", "total": "147.75", "count": 6},
            {"currency": "USD", "total": "30.00", "count": 1},
        ])
        bob = run_tool(self.bob, "get_spending_total", self.WIDE)
        self.assertEqual(bob["totals"], [
            {"currency": "JOD", "total": "800.00", "count": 2},
            {"currency": "USD", "total": "70.00", "count": 1},
        ])

    def test_by_category_never_includes_another_user(self):
        result = run_tool(self.alice, "get_spending_by_category", self.WIDE)
        self.assertEqual(sum(row["count"] for row in result["categories"]), 7)

    def test_list_and_top_never_include_another_user(self):
        for name, arguments in [
            ("list_expenses", {**self.WIDE, "limit": 50}),
            ("list_expenses", {**self.WIDE, "store": "Bob"}),
            ("get_top_expenses", {**self.WIDE, "limit": 50}),
        ]:
            with self.subTest(tool=name, arguments=arguments):
                result = run_tool(self.alice, name, arguments)
                self.assert_no_bob_stores(result)
        self.assertEqual(run_tool(self.alice, "list_expenses", {**self.WIDE, "store": "Bob"})["expenses"], [])

    def test_compare_never_includes_another_user(self):
        result = run_tool(self.alice, "compare_periods", {
            "first_start": "2026-09-01", "first_end": "2026-09-30",
            "second_start": "2026-10-01", "second_end": "2026-10-31",
        })
        self.assertEqual(result["comparison"][0]["first_total"], "25.00")

    def test_user_cannot_be_passed_as_an_argument(self):
        for name, arguments in [
            ("get_spending_total", {**self.WIDE, "user": self.bob.pk}),
            ("get_spending_total", {**self.WIDE, "user_id": self.bob.pk}),
        ]:
            with self.subTest(arguments=list(arguments)):
                self.assertIn("error", run_tool(self.alice, name, arguments))

    def test_no_schema_exposes_a_user_parameter(self):
        for schema in TOOL_SCHEMAS:
            self.assertFalse({"user", "user_id"} & set(schema["parameters"]["properties"]), schema["name"])


class RunToolErrorTests(TestCase):
    def setUp(self):
        self.user = make_user()
        make_category("food")

    def assert_error(self, name, arguments, contains=""):
        result = run_tool(self.user, name, arguments)
        self.assertEqual(list(result), ["error"])
        self.assertIn(contains, result["error"])

    def test_unknown_tool(self):
        self.assert_error("delete_all_expenses", {}, "Unknown tool")

    def test_bad_dates(self):
        for start, end in [
            ("2026-02-30", "2026-03-01"),
            ("01/10/2026", "2026-10-31"),
            ("last month", "2026-10-31"),
            ("", "2026-10-31"),
            (20261001, "2026-10-31"),
            (None, "2026-10-31"),
        ]:
            with self.subTest(start=start):
                self.assert_error("get_spending_total", {"start_date": start, "end_date": end}, "start_date")

    def test_start_after_end(self):
        self.assert_error("get_spending_total", {"start_date": "2026-10-31", "end_date": "2026-10-01"}, "on or before")
        self.assert_error("compare_periods", {
            "first_start": "2026-09-01", "first_end": "2026-09-30",
            "second_start": "2026-10-31", "second_end": "2026-10-01",
        }, "second_start")

    def test_missing_and_unexpected_arguments(self):
        self.assert_error("get_spending_total", {"start_date": "2026-10-01"}, "Invalid arguments")
        self.assert_error("get_spending_by_category", {**OCTOBER, "category": "food"}, "Invalid arguments")

    def test_arguments_must_be_an_object(self):
        self.assert_error("get_spending_total", ["2026-10-01", "2026-10-31"], "JSON object")
        self.assert_error("get_spending_total", None, "JSON object")

    def test_unknown_category_lists_the_valid_ones(self):
        self.assert_error("get_spending_total", {**OCTOBER, "category": "yachts"}, "Valid categories: Bills, Entertainment, Food, Health, Other, Shopping, Transport.")

    def test_bad_limit(self):
        for limit in [0, -3, "10", 2.5, True]:
            with self.subTest(limit=limit):
                self.assert_error("list_expenses", {**OCTOBER, "limit": limit}, "limit")

    def test_limit_is_capped(self):
        result = run_tool(self.user, "get_top_expenses", {**OCTOBER, "limit": 10_000})
        self.assertEqual(result["expenses"], [])
        self.assertNotIn("error", result)

    def test_every_schema_matches_its_function(self):
        self.assertEqual({s["name"] for s in TOOL_SCHEMAS}, set(tools.TOOLS))
        for schema in TOOL_SCHEMAS:
            with self.subTest(tool=schema["name"]):
                params = schema["parameters"]
                self.assertEqual(schema["type"], "function")
                self.assertTrue(schema["strict"])
                self.assertFalse(params["additionalProperties"])
                self.assertEqual(sorted(params["required"]), sorted(params["properties"]))
                # Calling with every parameter (as strict mode sends them) must not be an argument error.
                arguments = {key: None for key in params["properties"]}
                arguments.update({k: "2026-10-01" for k in arguments if k.endswith(("_date", "_start", "_end"))})
                self.assertNotIn("error", run_tool(self.user, schema["name"], arguments))
