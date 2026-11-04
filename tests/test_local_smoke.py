import os
import tempfile
import unittest

# Force une base SQLite isolée avant l'import du module, qui initialise sa base au chargement.
test_db = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{test_db.name}"
os.environ["SECRET_KEY"] = "test-only-secret"

import ticket_system_unified as application  # noqa: E402


class LocalSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        application.app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
        cls.client = application.app.test_client()

    def test_health_route(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_event_catalogue_route(self):
        response = self.client.get("/api/events")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.get_json(), list)

    def test_cart_starts_empty(self):
        response = self.client.get("/api/cart")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["items"], [])

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(test_db.name)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    unittest.main()
