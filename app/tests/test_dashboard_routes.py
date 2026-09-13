from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class DashboardRouteSourceTests(unittest.TestCase):
    def test_spa_fallback_includes_dashboard(self):
        pages = (ROOT / "app" / "routers" / "pages.py").read_text(encoding="utf-8")
        self.assertIn('"/dashboard"', pages)

    def test_frontend_uses_an_admin_guard_and_same_origin_grafana(self):
        app = (ROOT / "src" / "App.jsx").read_text(encoding="utf-8")
        dashboard = (ROOT / "src" / "pages" / "dashboard" / "DashboardPage.jsx").read_text(encoding="utf-8")
        self.assertIn("function AdminRoute", app)
        self.assertIn("user.role === 'admin'", app)
        self.assertIn('path="/dashboard"', app)
        self.assertIn("/grafana/d/", dashboard)
        self.assertNotIn("http://127.0.0.1:3000", dashboard)
        self.assertNotIn("Authorization", dashboard)
        self.assertIn("refresh=1m", dashboard)


if __name__ == "__main__":
    unittest.main()
