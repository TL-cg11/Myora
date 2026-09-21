from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class DashboardRouteSourceTests(unittest.TestCase):
    def test_spa_fallback_includes_dashboard(self):
        pages = (ROOT / "app" / "routers" / "pages.py").read_text(encoding="utf-8")
        self.assertIn('"/dashboard"', pages)

    def test_service_favicon_is_served_outside_grafana(self):
        pages = (ROOT / "app" / "routers" / "pages.py").read_text(encoding="utf-8")
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('"/favicon.svg"', pages)
        self.assertIn('/favicon.svg?v=20260917', index)

    def test_frontend_uses_an_admin_guard_and_same_origin_grafana(self):
        app = (ROOT / "src" / "App.jsx").read_text(encoding="utf-8")
        dashboard_dir = ROOT / "src" / "pages" / "dashboard"
        # Grafana URL 조립은 dashboardConfig.js 로 분리됐다. 페이지와 설정을 함께 검사한다.
        dashboard = "\n".join(
            (dashboard_dir / name).read_text(encoding="utf-8")
            for name in ("DashboardPage.jsx", "dashboardConfig.js")
        )
        self.assertIn("function AdminRoute", app)
        self.assertIn("user.role === 'admin'", app)
        self.assertIn('path="/dashboard"', app)
        self.assertIn("/grafana/d/", dashboard)
        self.assertNotIn("http://127.0.0.1:3000", dashboard)
        self.assertNotIn("Authorization", dashboard)
        # 새로고침 주기는 대시보드별 설정값으로 URL 에 들어간다 (기본 1m).
        self.assertIn("refresh=${dashboard.refresh}", dashboard)
        self.assertIn("refresh: '1m'", dashboard)


if __name__ == "__main__":
    unittest.main()
