"""Tests for the local web app, including its cross-site request protections."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import pytest

from expense_tracker.config import Config
from expense_tracker.ledger import Ledger
from expense_tracker.web import make_handler

from .test_cli import fake_categorize
from .test_integration import BOA_CHECKING_LINES, _write_pdf

pytest.importorskip("fpdf")


@pytest.fixture
def server(tmp_path):
    config = Config(home=tmp_path / "home")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    fake_categorize.calls = 0
    with patch("expense_tracker.categorizer.categorize_transactions", fake_categorize):
        yield f"http://127.0.0.1:{httpd.server_address[1]}", config
    httpd.shutdown()
    httpd.server_close()


def request(url, data=None, headers=None, method=None):
    headers = {"X-Expense-Tracker": "1", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_dashboard_is_editable(server):
    base, _ = server
    status, body = request(base + "/")
    assert status == 200
    assert b"const EDITABLE = true" in body


def test_upload_then_edit_category(server, tmp_path):
    base, config = server
    pdf = _write_pdf(tmp_path / "march.pdf", BOA_CHECKING_LINES).read_bytes()

    status, body = request(base + "/api/import?name=march.pdf", data=pdf)
    assert status == 200, body
    result = json.loads(body)
    assert result["message"] == "4 transactions (2 expenses, 1 income)."
    assert result["reconciled"] is True

    status, body = request(base + "/api/import?name=march.pdf", data=pdf)
    assert json.loads(body)["skipped"] is True

    data = json.loads(request(base + "/api/data")[1])
    txn = next(t for t in data["transactions"] if "TRADER" in t["description"])
    status, _ = request(
        f"{base}/api/transactions/{txn['id']}",
        data=json.dumps({"category": "Eating Out"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    assert status == 200
    with Ledger(config.db_path) as ledger:
        assert ledger.get_transaction(txn["id"])["category_source"] == "user"


def test_rejects_non_pdf_and_unknown_category(server):
    base, _ = server
    assert request(base + "/api/import?name=x.pdf", data=b"hello")[0] == 400
    body = json.dumps({"category": "Nope"}).encode()
    assert request(base + "/api/transactions/1", data=body)[0] == 400


def test_blocks_cross_site_writes(server):
    base, _ = server
    # A form post or fetch from another site cannot set the custom header without a preflight
    status, _ = request(base + "/api/import", data=b"%PDF-1.4", headers={"X-Expense-Tracker": ""})
    assert status == 403


def test_blocks_dns_rebinding(server):
    base, _ = server
    status, _ = request(base + "/api/data", headers={"Host": "evil.example:80"})
    assert status == 403


def test_category_change_without_remembering(server, tmp_path):
    base, config = server
    pdf = _write_pdf(tmp_path / "march.pdf", BOA_CHECKING_LINES).read_bytes()
    request(base + "/api/import?name=march.pdf", data=pdf)
    data = json.loads(request(base + "/api/data")[1])
    txn = next(t for t in data["transactions"] if "TRADER" in t["description"])

    body = json.dumps({"category": "Gifts", "remember": False}).encode()
    status, resp = request(f"{base}/api/transactions/{txn['id']}", data=body)

    assert status == 200 and json.loads(resp)["alsoUpdated"] == 0
    with Ledger(config.db_path) as ledger:
        assert ledger.get_rule("TRADER JOES")["source"] == "ai"  # the learned rule is untouched


def test_category_endpoint_rejects_oversized_or_malformed_bodies(server):
    base, _ = server
    assert request(base + "/api/transactions/1", data=b"x" * (70 * 1024))[0] == 400
    assert request(base + "/api/transactions/1", data=b"[1, 2]")[0] == 400
    assert request(base + "/api/transactions/1", data=b"not json")[0] == 400


def test_rename_merchant_endpoint(server, tmp_path):
    base, config = server
    pdf = _write_pdf(tmp_path / "march.pdf", BOA_CHECKING_LINES).read_bytes()
    request(base + "/api/import?name=march.pdf", data=pdf)
    txn = next(
        t for t in json.loads(request(base + "/api/data")[1])["transactions"] if "TRADER" in t["description"]
    )

    status, body = request(
        f"{base}/api/merchants/{txn['id']}", data=json.dumps({"name": "Trader Joe's"}).encode()
    )
    assert status == 200 and json.loads(body)["transactions"] == 1
    renamed = next(
        t for t in json.loads(request(base + "/api/data")[1])["transactions"] if t["id"] == txn["id"]
    )
    assert renamed["merchant"] == "Trader Joe's"

    assert (
        request(f"{base}/api/merchants/{txn['id']}", data=json.dumps({"name": "x" * 61}).encode())[0] == 400
    )
    assert request(f"{base}/api/merchants/{txn['id']}", data=json.dumps({"name": 5}).encode())[0] == 400
    assert request(f"{base}/api/merchants/999", data=json.dumps({"name": "X"}).encode())[0] == 400
    assert (
        request(f"{base}/api/merchants/{txn['id']}", data=b"{}", headers={"X-Expense-Tracker": ""})[0] == 403
    )
