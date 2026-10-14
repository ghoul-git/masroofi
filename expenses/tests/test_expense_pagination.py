import datetime

from django.test import TestCase

from expenses.tests.factories import make_category, make_expense, make_user


class ExpensePaginationTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        bob = make_user("bob")
        food = make_category()
        start = datetime.date(2026, 1, 1)
        for day in range(25):
            make_expense(self.alice, food, f"Shop {day}", date=(start + datetime.timedelta(days=day)).isoformat())
        for _ in range(3):
            make_expense(bob, food, "Bob Market")
        self.client.force_login(self.alice)

    def test_first_page_has_20_newest_expenses_and_a_next_link(self):
        body = self.client.get("/api/expenses/").json()
        self.assertEqual(body["count"], 25)
        self.assertEqual(len(body["results"]), 20)
        self.assertEqual(body["results"][0]["store_name"], "Shop 24")
        self.assertIsNone(body["previous"])
        self.assertTrue(body["next"].endswith("/api/expenses/?page=2"))

    def test_second_page_has_the_rest(self):
        body = self.client.get("/api/expenses/?page=2").json()
        self.assertEqual(body["count"], 25)
        self.assertEqual([e["store_name"] for e in body["results"]], [f"Shop {d}" for d in range(4, -1, -1)])
        self.assertIsNone(body["next"])
        self.assertIsNotNone(body["previous"])

    def test_pages_do_not_overlap_and_never_include_another_user(self):
        ids = []
        for page in [1, 2]:
            results = self.client.get(f"/api/expenses/?page={page}").json()["results"]
            ids += [e["id"] for e in results]
            self.assertNotIn("Bob Market", [e["store_name"] for e in results])
        self.assertEqual(len(ids), 25)
        self.assertEqual(len(set(ids)), 25)

    def test_page_past_the_end_returns_404(self):
        self.assertEqual(self.client.get("/api/expenses/?page=3").status_code, 404)

    def test_empty_list(self):
        self.client.force_login(make_user("carol"))
        self.assertEqual(self.client.get("/api/expenses/").json(), {"count": 0, "next": None, "previous": None, "results": []})

    def test_expenses_page_has_pagination_controls(self):
        html = self.client.get("/expenses/").content.decode()
        for element_id in ["pagination", "previous-page", "next-page", "page-info"]:
            self.assertIn(f'id="{element_id}"', html)
