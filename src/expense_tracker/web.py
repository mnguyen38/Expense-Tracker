"""Local web app: the dashboard plus PDF upload and category editing. Standard library only."""

import json
import re
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import Config
from .ledger import Ledger, merchant_key
from .pipeline import categorize_pending, import_statement, name_merchants, rename_merchant
from .report import dashboard_data, render_dashboard

MAX_UPLOAD_BYTES = 30 * 1024 * 1024

# SQLite writes and Claude calls are serialized; this is a single-user local app
_lock = threading.Lock()


def make_handler(config: Config, demo: bool = False):
    class Handler(BaseHTTPRequestHandler):
        def _trusted(self) -> bool:
            """
            Reject requests another website could make from the user's browser.

            The Host check defeats DNS rebinding; the custom header on writes forces
            a CORS preflight, which this server never approves.
            """
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if host not in ("127.0.0.1", "localhost"):
                return False
            return self.command == "GET" or self.headers.get("X-Expense-Tracker") == "1"

        def do_GET(self):
            if not self._trusted():
                return self._json(403, {"error": "Forbidden"})
            path = urlparse(self.path).path
            if path == "/":
                with Ledger(config.db_path) as ledger:
                    page = render_dashboard(dashboard_data(ledger, config), editable=True, demo=demo)
                self._send(200, page.encode(), "text/html; charset=utf-8")
            elif path == "/api/data":
                with Ledger(config.db_path) as ledger:
                    self._json(200, dashboard_data(ledger, config))
            else:
                self._json(404, {"error": "Not found"})

        def do_POST(self):
            if not self._trusted():
                return self._json(403, {"error": "Forbidden"})
            url = urlparse(self.path)
            if url.path == "/api/import":
                self._import(parse_qs(url.query).get("name", ["statement.pdf"])[0])
            elif m := re.fullmatch(r"/api/transactions/(\d+)", url.path):
                self._set_category(int(m.group(1)))
            elif m := re.fullmatch(r"/api/merchants/(\d+)", url.path):
                self._rename(int(m.group(1)))
            else:
                self._json(404, {"error": "Not found"})

        def _import(self, name: str):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if not 0 < length <= MAX_UPLOAD_BYTES:
                return self._json(400, {"error": "Upload a PDF under 30 MB"})
            body = self.rfile.read(length)
            if not body.startswith(b"%PDF"):
                return self._json(400, {"error": f"{name} is not a PDF"})

            safe_name = Path(name).name or "statement.pdf"
            with tempfile.TemporaryDirectory() as tmp, _lock, Ledger(config.db_path) as ledger:
                pdf = Path(tmp) / safe_name
                pdf.write_bytes(body)
                try:
                    result = import_statement(ledger, config, pdf)
                    if not result.skipped:
                        categorize_pending(ledger, config)
                        try:
                            name_merchants(ledger, config)
                        except Exception as e:  # a nicety; the import itself succeeded
                            print(f"  Couldn't name new merchants: {e}")
                except Exception as e:
                    return self._json(422, {"error": str(e)})

            if result.skipped:
                message = "Already imported."
            else:
                message = f"{result.transaction_count} transactions ({result.expense_count} expenses, {result.income_count} income)."
            self._json(
                200,
                {
                    "message": message,
                    "skipped": result.skipped,
                    "reconciled": result.reconciled,
                    "warnings": result.warnings,
                },
            )

        def _set_category(self, txn_id: int):
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if not 0 <= length <= 64 * 1024:
                    return self._json(400, {"error": "Request too large"})
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json(400, {"error": "Invalid request"})
            if not isinstance(body, dict):
                return self._json(400, {"error": "Invalid request"})
            category = body.get("category")
            if category not in config.categories:
                return self._json(400, {"error": f"Unknown category: {category}"})

            with _lock, Ledger(config.db_path) as ledger:
                txn = ledger.get_transaction(txn_id)
                if txn is None:
                    return self._json(404, {"error": "No such transaction"})
                ledger.set_category(txn_id, category, "user")
                updated = 0
                if body.get("remember", True):
                    # Remember the merchant and apply it to its other transactions
                    key = merchant_key(txn["description"])
                    ledger.save_rule(key, category, "user")
                    updated = ledger.recategorize_merchant(key, category)
            self._json(200, {"ok": True, "alsoUpdated": updated})

        def _rename(self, txn_id: int):
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if not 0 <= length <= 4096:
                    return self._json(400, {"error": "Request too large"})
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json(400, {"error": "Invalid request"})
            if not isinstance(body, dict) or not isinstance(body.get("name", ""), str):
                return self._json(400, {"error": "Invalid request"})
            with _lock, Ledger(config.db_path) as ledger:
                try:
                    _, count = rename_merchant(ledger, txn_id, body.get("name", ""))
                except ValueError as e:
                    return self._json(400, {"error": str(e)})
            self._json(200, {"ok": True, "transactions": count})

        def _json(self, status: int, data: dict):
            self._send(status, json.dumps(data).encode(), "application/json")

        def _send(self, status: int, body: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):  # quieter than the default access log
            if not self.path.startswith("/api/data"):
                print(f"  {self.command} {self.path.split('?')[0]} -> {args[1] if len(args) > 1 else ''}")

    return Handler


def serve(config: Config, port: int = 8765, open_browser: bool = True, demo: bool = False) -> None:
    # Bound to localhost only: the ledger holds personal financial data
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(config, demo))
    url = f"http://127.0.0.1:{port}/"
    print(f"Expense Tracker running at {url}  (Ctrl+C to stop)")
    print(f"Data: {config.db_path}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
