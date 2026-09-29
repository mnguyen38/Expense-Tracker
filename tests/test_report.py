"""Tests for the self-contained report page."""

import re

from expense_tracker.config import Config
from expense_tracker.demo import build_demo
from expense_tracker.ledger import Ledger
from expense_tracker.report import dashboard_data, demo_banner, render_dashboard


def _page(tmp_path, **kwargs):
    config = Config(home=tmp_path)
    with Ledger(":memory:") as ledger:
        build_demo(ledger, config, months=3)
        return render_dashboard(dashboard_data(ledger, config), **kwargs)


def test_page_makes_no_external_requests(tmp_path):
    page = _page(tmp_path, demo=True, banner=demo_banner())
    # Only the GitHub link (an <a href>) and SVG namespaces may appear; no src/url() to the network
    assert not re.search(r"""(src|href)=["']https?://(?!github\.com)""", page)
    assert "url(http" not in page
    assert "@import" not in page


def test_fonts_are_inlined(tmp_path):
    page = _page(tmp_path)
    for family in ("Fraunces", "Figtree", "DM Mono"):
        assert f"font-family:'{family}'" in page
    assert "data:font/woff2;base64," in page


def test_demo_and_editable_flags(tmp_path):
    demo = _page(tmp_path, demo=True)
    assert "const DEMO = true" in demo and "const EDITABLE = false" in demo
    app = _page(tmp_path, editable=True)
    assert "const EDITABLE = true" in app and "const DEMO = false" in app


def test_data_links_transactions_to_statements(tmp_path):
    config = Config(home=tmp_path)
    with Ledger(":memory:") as ledger:
        build_demo(ledger, config, months=2)
        data = dashboard_data(ledger, config)
    statement_ids = {s["id"] for s in data["statements"]}
    assert all(t["statementId"] in statement_ids for t in data["transactions"])
    assert {t["categorySource"] for t in data["transactions"] if t["kind"] == "expense"} >= {"rule", "ai"}
    assert all(s["importedAt"] for s in data["statements"])


def test_merchant_text_cannot_break_out_of_the_script(tmp_path):
    config = Config(home=tmp_path)
    with Ledger(":memory:") as ledger:
        ledger.add_email_transactions(
            [
                {
                    "email_id": "x",
                    "date": "2026-01-02",
                    "description": "</script><img src=x onerror=alert(1)>",
                    "amount": -1,
                }
            ]
        )
        page = render_dashboard(dashboard_data(ledger, config))
    script = page.split("const DATA = ")[1].split("\nconst EDITABLE")[0]
    assert "</script>" not in script
