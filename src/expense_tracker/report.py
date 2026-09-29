"""The monthly report: a self-contained HTML page built from the ledger (no external assets)."""

import html
import json
from datetime import date, datetime
from pathlib import Path

from ._fonts import FONT_CSS
from .config import Config
from .ledger import Ledger, display_name, merchant_key, month_label

REPO_URL = "https://github.com/mnguyen38/Expense-Tracker"


def dashboard_data(ledger: Ledger, config: Config) -> dict:
    """Everything the report needs, as plain JSON-serializable data."""
    this_month = date.today().strftime("%Y-%m")
    months = []
    for month in ledger.months():
        s = ledger.month_summary(month)
        months.append(
            {
                "month": month,
                "label": month_label(month),
                "spending": s["total_spending"],
                "income": s["total_income"],
                "partial": month == this_month,
            }
        )

    # A name you gave, or Claude's clean name, before the built-in tidy-up
    names = ledger.names()
    transactions = [
        {
            "id": t["id"],
            "statementId": t["statement_id"],
            "date": t["date"],
            "month": t["month"],
            "description": t["description"],
            "merchant": names.get(merchant_key(t["description"])) or display_name(t["description"]),
            "amount": t["amount"],
            "kind": t["kind"],
            "category": t["category"],
            "categorySource": t["category_source"],
            "source": t["source"],
        }
        for t in ledger.transactions()
    ]

    statements = [
        {
            "id": s["id"],
            "fileName": s["file_name"],
            "bank": s["bank_name"],
            "account": s["account_type"],
            "month": s["month"],
            "opening": s["opening_balance"],
            "closing": s["closing_balance"],
            "periodStart": s["period_start"],
            "periodEnd": s["period_end"],
            "reconciled": None if s["reconciled"] is None else bool(s["reconciled"]),
            "warnings": json.loads(s["warnings"] or "[]"),
            "importedAt": s["imported_at"],
        }
        for s in ledger.statements()
    ]

    now = datetime.now()
    return {
        "printedAt": f"{now.day} {now.strftime('%B %Y, %H:%M')}".upper(),
        "currency": config.currency_symbol,
        "categories": config.category_names,
        "months": months,
        "transactions": transactions,
        "statements": statements,
    }


def render_dashboard(
    data: dict, editable: bool = False, demo: bool = False, banner: str | None = None
) -> str:
    """
    Render the report page.

    editable: upload and category editing, for the `serve` web app.
    demo: marks the page as synthetic data and swaps the upload area for install instructions.
    banner: optional notice above the page (may contain HTML).
    """
    payload = json.dumps(data).replace("</", "<\\/")
    return (
        TEMPLATE.replace("__FONTS__", FONT_CSS)
        .replace("__BANNER__", f'<div class="banner">{banner}</div>' if banner else "")
        .replace("__DATA__", payload)
        .replace("__EDITABLE__", "true" if editable else "false")
        .replace("__DEMO__", "true" if demo else "false")
        .replace("__REPO__", html.escape(REPO_URL, quote=True))
    )


def write_dashboard(
    ledger: Ledger,
    config: Config,
    output: Path | None = None,
    banner: str | None = None,
    demo: bool = False,
) -> Path:
    output = Path(output) if output else config.home / "dashboard.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_dashboard(dashboard_data(ledger, config), banner=banner, demo=demo), encoding="utf-8"
    )
    return output


def demo_banner(repo_url: str = REPO_URL) -> str:
    url = html.escape(repo_url, quote=True)
    return f'Live demo with synthetic data. Nothing here is real. <a href="{url}">View the code on GitHub</a>'


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Expense Tracker · Monthly report</title>
<style>
__FONTS__
:root {
  color-scheme: light;
  --bg: #F3EEE3; --paper: #FFFDF8; --paper-soft: #F8F4EA; --ink: #1F1B16; --muted: #6B6358; --rule: #D6CCB8;
  --green: #2F6B4F; --stamp: #B4432F; --housing: #3F51A3; --groceries: #2E7D7A; --eating: #B7791F; --bills: #8E3B6E;
  --other: #A0978A; --claude: #6B4FB3; --btn-bg: #1F1B16; --btn-fg: #FFFDF8; --shadow: rgba(60,45,20,.16);
  --coin-ring: rgba(255,255,255,.28); --weekend: rgba(31,27,22,.025);
  --hl: rgba(233,196,106,.34); --hl-line: rgba(183,121,31,.38);
  --serif: 'Fraunces', 'Iowan Old Style', 'Palatino Linotype', Georgia, serif;
  --sans: 'Figtree', system-ui, -apple-system, 'Segoe UI', sans-serif;
  --mono: 'DM Mono', ui-monospace, 'SF Mono', Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --bg: #15130E; --paper: #221E17; --paper-soft: #1C1913; --ink: #EFE7D6; --muted: #A89F8E; --rule: #3A352B;
    --green: #86CFA6; --stamp: #E58B6E; --housing: #9AA8F0; --groceries: #6FC3BF; --eating: #E3B35A; --bills: #D98BB9;
    --other: #8C8474; --claude: #B9A2F0; --btn-bg: #EFE7D6; --btn-fg: #15130E; --shadow: rgba(0,0,0,.45);
    --coin-ring: rgba(255,255,255,.14); --weekend: rgba(239,231,214,.03);
    --hl: rgba(227,179,90,.17); --hl-line: rgba(227,179,90,.42);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #15130E; --paper: #221E17; --paper-soft: #1C1913; --ink: #EFE7D6; --muted: #A89F8E; --rule: #3A352B;
  --green: #86CFA6; --stamp: #E58B6E; --housing: #9AA8F0; --groceries: #6FC3BF; --eating: #E3B35A; --bills: #D98BB9;
  --other: #8C8474; --claude: #B9A2F0; --btn-bg: #EFE7D6; --btn-fg: #15130E; --shadow: rgba(0,0,0,.45);
  --coin-ring: rgba(255,255,255,.14); --weekend: rgba(239,231,214,.03);
  --hl: rgba(227,179,90,.17); --hl-line: rgba(227,179,90,.42);
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
html { background: var(--bg); }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.5 var(--sans); transition: background-color .4s ease, color .4s ease; }
a { color: inherit; text-underline-offset: 3px; }
button { font: inherit; color: inherit; cursor: pointer; }
:focus-visible { outline: 2px solid var(--ink); outline-offset: 3px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.banner { background: var(--ink); color: var(--paper); text-align: center; padding: 8px 16px; font: 13px var(--sans); }
.banner a { color: var(--paper); }
.page { max-width: 1440px; margin: 0 auto; padding: 44px 64px 40px; display: flex; flex-direction: column; gap: 56px; }
.label { font: 500 12px var(--mono); letter-spacing: .12em; color: var(--muted); text-transform: uppercase; }
.label-sm { font: 11px var(--mono); letter-spacing: .1em; color: var(--muted); text-transform: uppercase; }
.muted { color: var(--muted); }
.mono { font-family: var(--mono); }
.double-rule { height: 4px; border-top: 1.5px solid var(--ink); border-bottom: 1px solid var(--ink); }
.double-rule.flip { border-top-width: 1px; border-bottom-width: 1.5px; }

/* masthead */
header.mast { display: flex; flex-direction: column; gap: 18px; }
.mast-row { display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap; }
.brand { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
.brand .title { font: 600 26px var(--serif); letter-spacing: -.01em; }
.monthnav { display: flex; align-items: center; gap: 6px; }
.monthnav .current { font: italic 400 22px var(--serif); padding: 0 14px; width: 220px; text-align: center; white-space: nowrap; }
.round { width: 44px; height: 44px; border-radius: 999px; border: 1px solid var(--rule); background: transparent; display: inline-flex; align-items: center; justify-content: center; font-size: 18px; }
.round:disabled { opacity: .35; cursor: default; }
.mast-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.local { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); }
.local .dot { width: 7px; height: 7px; border-radius: 999px; background: var(--green); }
.pill-btn { height: 44px; padding: 0 20px; border-radius: 999px; border: 0; background: var(--btn-bg); color: var(--btn-fg); font-size: 14px; font-weight: 600; display: inline-flex; align-items: center; text-decoration: none; }

/* hero */
.hero { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); column-gap: 40px; align-items: start; }
.hero-text { grid-column: span 7; display: flex; flex-direction: column; gap: 28px; padding-top: 12px; }
h1 { margin: 0; font: 500 clamp(44px, 5.6vw, 80px)/1.02 var(--serif); letter-spacing: -.025em; }
h1 .win { color: var(--green); text-decoration: underline wavy var(--green); text-decoration-thickness: 3px; text-underline-offset: .2em; text-decoration-skip-ink: none; }
h1 .loss { color: var(--stamp); }
.lede { margin: 0; max-width: 620px; font: italic 400 23px/1.45 var(--serif); color: var(--muted); }
.figures { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: 8px; border-top: 1px solid var(--rule); }
.figures > div { padding: 20px 20px 0; display: flex; flex-direction: column; gap: 6px; border-left: 1px solid var(--rule); min-width: 0; }
.figures > div:first-child { padding-left: 0; border-left: 0; }
.figures .value { font: 500 34px var(--serif); font-variant-numeric: lining-nums; }
.figures .sub { font-size: 13px; color: var(--muted); }
.good { color: var(--green) !important; } .bad { color: var(--stamp) !important; }
.checks { grid-column: span 5; position: relative; z-index: 2; padding: 8px 0 146px 40px; display: flex; flex-direction: column; }
.receipt { width: 380px; max-width: 100%; filter: drop-shadow(0 18px 30px var(--shadow)); }
/* Several statements stack into a deck: peek on hover, deal out to the left on click */
.deck { position: relative; width: 380px; max-width: 100%; outline: none; }
.deck > .receipt { position: absolute; top: 0; left: 0; transform: var(--rest); transform-origin: 50% 90%; transition: transform .45s cubic-bezier(.2, .8, .2, 1); }
.deck.single > .receipt { position: relative; transform: rotate(1.6deg); }
.deck:not(.single) { cursor: pointer; }
.deck:not(.single):not(.open):hover > .receipt, .deck:not(.single):not(.open):focus-visible > .receipt { transform: var(--peek); }
.deck.open > .receipt { transform: var(--spread); }
.deck.open > .receipt:hover { z-index: 50 !important; }  /* overlapped cards: hover one to read it */
.deck:focus-visible { outline: 2px solid var(--ink); outline-offset: 10px; border-radius: 4px; }
.deck-hint { position: absolute; left: 40px; bottom: 56px; font: 11px var(--mono); letter-spacing: .08em; color: var(--muted); text-transform: uppercase; }
.receipt .body { background: var(--paper); padding: 30px 30px 34px; font: 13px var(--mono); display: flex; flex-direction: column; gap: 10px; }
.receipt .center { text-align: center; }
.receipt .head { letter-spacing: .14em; font-weight: 500; }
.receipt .dash { border-top: 1.5px dashed var(--rule); margin: 4px 0; }
.receipt .line { display: flex; justify-content: space-between; gap: 12px; }
.receipt .line.total { font-weight: 500; }
.receipt .line.flag { background: color-mix(in srgb, var(--stamp) 14%, transparent); color: var(--stamp); margin: 0 -8px; padding: 2px 8px; }
.receipt .note { font-size: 11px; color: var(--muted); }
.receipt svg { display: block; width: 100%; height: 14px; }
.stamp { position: absolute; left: 318px; bottom: 0; width: 176px; height: 176px; transform: rotate(-14deg); opacity: .92; }
.stamp.muted { opacity: .7; }

/* sections */
.sec-head { display: flex; align-items: baseline; gap: 18px; border-bottom: 1px solid var(--rule); padding-bottom: 14px; flex-wrap: wrap; }
.sec-head .num { font: 22px var(--serif); color: var(--muted); }
h2 { margin: 0; font: 500 34px var(--serif); letter-spacing: -.01em; }
h3 { margin: 0; font: 500 24px var(--serif); padding-bottom: 12px; border-bottom: 1px solid var(--rule); }
.sec-head .hint { margin-left: auto; font-size: 13px; color: var(--muted); }
section.block { display: flex; flex-direction: column; gap: 28px; }
.three { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); column-gap: 40px; align-items: start; }
.coins { grid-column: span 4; display: grid; grid-template-columns: repeat(10, minmax(0, 1fr)); gap: 8px; }
.coins span { aspect-ratio: 1; border-radius: 999px; box-shadow: inset 0 0 0 3px var(--coin-ring); }
.key { grid-column: span 4; display: flex; flex-direction: column; }
.key-row { display: grid; grid-template-columns: 22px 64px minmax(0, 1fr) auto; align-items: center; gap: 12px; padding: 13px 0; border-bottom: 1px solid var(--rule); }
.swatch { width: 16px; height: 16px; border-radius: 999px; }
.key-row .n { font: 500 26px var(--serif); font-variant-numeric: lining-nums; }
.key-row .amt { font: 13px var(--mono); color: var(--muted); }
.margin { grid-column: span 4; display: flex; flex-direction: column; gap: 22px; padding-left: 28px; border-left: 1px solid var(--rule); }
.margin .item { display: flex; gap: 14px; }
.margin .roman { font: 20px var(--serif); min-width: 22px; }
.margin p { margin: 0; font: italic 400 19px/1.45 var(--serif); }

/* diary */
.diary-wrap { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); column-gap: 40px; align-items: start; }
.diary-main { grid-column: span 8; display: flex; flex-direction: column; gap: 22px; min-width: 0; }
.side { grid-column: span 4; display: flex; flex-direction: column; gap: 40px; }
table.diary { width: 100%; border-collapse: collapse; table-layout: fixed; }
.diary th { font: 11px var(--mono); letter-spacing: .1em; color: var(--muted); text-align: left; font-weight: 400; padding: 0 0 8px; }
.diary th:last-child, .diary td.week { width: 96px; text-align: right; }
.diary tbody tr { height: 96px; border-top: 1px solid var(--rule); }
.diary tbody tr:last-child { border-bottom: 1px solid var(--rule); }
.diary td { position: relative; padding: 0; vertical-align: top; }
.diary td.we { background: var(--weekend); }
.diary .d { position: absolute; left: 2px; top: 8px; font: 15px var(--serif); font-variant-numeric: lining-nums; }
.diary .d small { font: 10px var(--mono); letter-spacing: .06em; color: var(--muted); margin-left: 3px; }
.diary .dot { position: absolute; left: 50%; top: calc(50% + 6px); display: block; overflow: visible; color: var(--ink); }
.diary-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 20px; font-size: 12px; color: var(--muted); }
.diary-legend span { display: inline-flex; align-items: center; gap: 8px; }
.diary-legend svg { color: var(--ink); overflow: visible; }
.diary-legend .legend-colours { flex-wrap: wrap; gap: 4px 8px; }
.diary-legend .legend-colours i { display: inline-block; width: 9px; height: 9px; border-radius: 999px; margin-left: 4px; }
.dragging .picked { pointer-events: none; opacity: .3; transition: opacity .15s ease; }
.dragging, .dragging * { cursor: grabbing !important; }
.diary td.week { vertical-align: middle; font: 18px var(--serif); font-variant-numeric: lining-nums; }
.diary button.day { position: absolute; inset: 0; z-index: 1; width: 100%; height: 100%; padding: 0; border: 0; background: transparent; text-align: left; cursor: pointer; touch-action: manipulation; -webkit-user-select: none; user-select: none; }
.diary button.day::after { content: ""; position: absolute; inset: 6px 4px; border-radius: 12px; transition: background-color .15s ease; }
.diary button.day:hover::after { background: color-mix(in srgb, var(--hl) 45%, transparent); }
/* Selected days look highlighted with a marker; neighbours in a week join into one stroke */
.diary td.sel::before { content: ""; position: absolute; inset: 6px 4px; background: var(--hl); border: 1px solid var(--hl-line); border-radius: 12px; }
.diary td.sel.jl::before { left: 0; border-left: 0; border-top-left-radius: 0; border-bottom-left-radius: 0; }
.diary td.sel.jr::before { right: 0; border-right: 0; border-top-right-radius: 0; border-bottom-right-radius: 0; }
.diary td.sel .d { font-weight: 600; }
.diary button.wk { font: inherit; background: none; border: 0; padding: 4px 0 4px 8px; cursor: pointer; text-decoration: underline dotted var(--rule); text-underline-offset: 5px; }
.diary button.wk:hover { text-decoration-color: var(--ink); }
.pick-hint { margin: 0; font-size: 13px; color: var(--muted); }
.side { align-self: stretch; }
.picked { position: sticky; top: 16px; display: flex; flex-direction: column; background: var(--paper); border: 1px solid var(--rule); border-radius: 16px; box-shadow: 0 18px 40px var(--shadow); overflow: hidden; }
@media (min-width: 1101px) { .side.picking > :not(.picked) { display: none !important; } }
.pick-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; padding: 18px 20px 14px; border-bottom: 1px dashed var(--rule); }
.pick-total { font: 500 30px/1.1 var(--serif); font-variant-numeric: lining-nums; margin-top: 4px; }
.pick-sub { font-size: 13px; color: var(--muted); margin-top: 4px; }
.pick-more { display: none; flex: none; height: 36px; padding: 0 14px; border-radius: 999px; border: 0; background: var(--btn-bg); color: var(--btn-fg); font-size: 13px; font-weight: 600; align-items: center; }
.pick-actions { display: flex; gap: 8px; flex: none; }
.pick-clear { flex: none; height: 36px; padding: 0 14px; border-radius: 999px; border: 1px solid var(--rule); background: transparent; font-size: 13px; }
.pick-scroll { overflow-y: auto; overscroll-behavior: contain; padding: 4px 20px 16px; }
.pick-day { padding: 12px 0 6px; }
.pick-day + .pick-day { border-top: 1px dashed var(--rule); }
.pick-date { display: flex; justify-content: space-between; align-items: baseline; font: 17px var(--serif); margin-bottom: 2px; font-variant-numeric: lining-nums; }
.pick-date .mono { font-size: 13px; }
.pick-row { display: grid; grid-template-columns: 10px minmax(0, 1fr) auto; gap: 10px; align-items: baseline; padding: 5px 0; font-size: 14px; }
.pick-row .cdot { width: 9px; height: 9px; border-radius: 999px; }
.pick-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pick-name small { display: block; font-size: 11px; color: var(--muted); }
.pick-row .mono { font-size: 13px; }
.pick-none { padding: 12px 0 4px; border-top: 1px dashed var(--rule); font-size: 13px; color: var(--muted); }
@media (max-width: 1100px) {
  /* Below the side-by-side layout the list becomes a bottom sheet over the page */
  .picked { position: fixed; top: auto; left: 16px; right: 16px; bottom: 12px; margin: 0 auto; max-width: 640px; max-height: 46vh !important; z-index: 40; animation: sheet-in .22s ease-out; }
  .picked:not(.expanded) .pick-scroll { display: none; }
  .picked:not(.expanded) .pick-top { border-bottom: 0; padding-bottom: 16px; }
  .picked .pick-more { display: inline-flex; }
  html.sheet-open { scroll-padding-bottom: var(--sheet-view, 0px); }
  html.sheet-open body { padding-bottom: var(--sheet, 0px); }
  @keyframes sheet-in { from { transform: translateY(24px); opacity: 0; } }
}
@media (prefers-reduced-motion: reduce) { .picked { animation: none; } .diary button.day::after { transition: none; } }
.diary td.pending { background: repeating-linear-gradient(135deg, transparent 0 7px, color-mix(in srgb, var(--rule) 55%, transparent) 7px 8px); }
.diary td.pending .d { color: var(--muted); }
.diary-note { margin: -8px 0 0; font: italic 400 16px/1.45 var(--serif); color: var(--muted); }
details.spill { border-top: 1px solid var(--rule); }
details.spill summary { list-style: none; cursor: pointer; display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 14px; padding: 14px 0; font-size: 14px; min-height: 44px; }
details.spill summary::-webkit-details-marker { display: none; }
details.spill .spill-title { font: 500 18px var(--serif); }
details.spill .spill-open { margin-left: auto; font: 11px var(--mono); letter-spacing: .1em; text-transform: uppercase; color: var(--muted); text-decoration: underline; text-underline-offset: 3px; }
details.spill .spill-open::before { content: "Show"; }
details.spill[open] .spill-open::before { content: "Hide"; }
.diary.spill-table tbody tr { height: 72px; }
.diary.spill-table { margin-bottom: 8px; }
.tally-row { display: flex; flex-direction: column; gap: 6px; }
.tally-row .top { display: flex; justify-content: space-between; font-size: 14px; }
.tally { display: flex; flex-wrap: wrap; gap: 6px; }
.side-note { margin: 0; font: italic 400 16px/1.45 var(--serif); color: var(--muted); }
.payee { display: flex; align-items: baseline; gap: 12px; padding: 8px 0; font-size: 15px; }
.payee .rank { font: 18px var(--serif); color: var(--muted); width: 18px; }
.payee .name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.payee .leader { flex: 1; border-bottom: 2px dotted var(--rule); transform: translateY(-4px); min-width: 16px; }
.payee .amt { font: 14px var(--mono); white-space: nowrap; }

/* ledger */
.drop { position: relative; display: flex; align-items: center; gap: 22px; padding: 22px 28px; border-radius: 18px; border: 1.5px dashed var(--rule); background: var(--paper-soft); cursor: pointer; flex-wrap: wrap; }
.drop.over { border-color: var(--ink); background: var(--paper); }
.drop:focus-within { outline: 2px solid var(--ink); outline-offset: 3px; }
.drop .big { font: 500 21px var(--serif); }
.drop .small { font-size: 14px; color: var(--muted); }
.drop .browse { text-decoration: underline; text-underline-offset: 3px; color: var(--ink); }
.drop input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.drop .status { margin-left: auto; font: 12px var(--mono); color: var(--muted); display: flex; flex-direction: column; gap: 4px; align-items: flex-end; text-align: right; }
.try { padding: 22px 28px; border-radius: 18px; border: 1.5px dashed var(--rule); background: var(--paper-soft); display: flex; gap: 22px; align-items: center; flex-wrap: wrap; }
.try code { font: 13px var(--mono); background: var(--paper); border: 1px solid var(--rule); border-radius: 8px; padding: 6px 10px; display: inline-block; overflow-wrap: anywhere; }
.pills { display: flex; gap: 8px; flex-wrap: wrap; font-size: 14px; }
.pills button { height: 40px; padding: 0 16px; border-radius: 999px; border: 1px solid var(--rule); background: transparent; }
.pills button[aria-pressed="true"] { background: var(--btn-bg); color: var(--btn-fg); border-color: var(--btn-bg); font-weight: 600; }
.ledger { display: flex; flex-direction: column; }
.lrow { display: grid; grid-template-columns: 110px minmax(0, 1.5fr) minmax(40px, 1fr) 200px 130px 130px; gap: 16px; align-items: center; min-height: 64px; border-bottom: 1px solid var(--rule); position: relative; }
.lrow.head { min-height: 0; padding-bottom: 10px; border-bottom: 1.5px solid var(--ink); font: 11px var(--mono); letter-spacing: .1em; color: var(--muted); }
.lrow .date { font: 17px var(--serif); font-variant-numeric: lining-nums; }
.lrow .who { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.lrow .who b { font-size: 16px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rename { font: inherit; color: inherit; background: none; border: 0; padding: 0; text-align: left; cursor: text; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-flex; align-items: center; gap: 6px; }
.rename svg { opacity: 0; transition: opacity .15s ease; flex: none; color: var(--muted); }
.rename:hover svg, .rename:focus-visible svg { opacity: 1; }
.rename:hover .rn { text-decoration: underline dotted var(--muted); text-underline-offset: 4px; }
.rename-input { font: 500 16px var(--sans); color: var(--ink); background: var(--paper); border: 1px solid var(--ink); border-radius: 8px; padding: 3px 8px; width: min(100%, 300px); }
.lrow .who small { font: 11px var(--mono); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lrow .leader { border-bottom: 2px dotted var(--rule); }
.lrow .by { font-size: 13px; color: var(--muted); display: flex; align-items: center; gap: 6px; }
.lrow .by.claude { color: var(--claude); }
.lrow .money { text-align: right; font: 15px var(--mono); white-space: nowrap; }
.cat { display: inline-flex; align-items: center; gap: 8px; height: 36px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--rule); background: transparent; font-size: 14px; max-width: 100%; white-space: nowrap; }
button.cat[aria-expanded="true"] { border-color: var(--ink); background: var(--paper); }
span.cat { cursor: default; }
.cat .cdot, .opt .cdot { width: 9px; height: 9px; border-radius: 999px; flex: none; }
.cat .cname { overflow: hidden; text-overflow: ellipsis; }
.popover { position: absolute; z-index: 20; width: 250px; padding: 8px; border-radius: 14px; background: var(--paper); border: 1px solid var(--rule); box-shadow: 0 18px 40px var(--shadow); display: flex; flex-direction: column; font-size: 14px; opacity: 0; transition: opacity .15s ease; }
.popover.open { opacity: 1; }
.popover [role="listbox"] { display: flex; flex-direction: column; max-height: 300px; overflow-y: auto; outline: none; }
.opt { display: flex; align-items: center; gap: 10px; min-height: 38px; padding: 0 10px; border-radius: 9px; cursor: pointer; }
.opt.active { background: var(--paper-soft); outline: 1px solid var(--rule); }
.opt .tick { margin-left: auto; color: var(--green); }
.popover hr { border: 0; height: 1px; background: var(--rule); margin: 6px 4px; }
.popover label { display: flex; align-items: center; gap: 10px; padding: 8px 10px; font-size: 13px; color: var(--muted); cursor: pointer; }
.popover input { accent-color: var(--green); width: 16px; height: 16px; }
.ledger-foot { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; font-size: 14px; color: var(--muted); }
.ledger-foot .links { display: flex; gap: 20px; flex-wrap: wrap; }
.ledger-foot button { background: none; border: 0; padding: 0; text-decoration: underline; text-underline-offset: 3px; color: var(--muted); min-height: 24px; }
.ledger-foot button.primary { color: var(--ink); }
footer { display: flex; flex-direction: column; gap: 14px; }
footer .row { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.empty-hero { display: flex; flex-direction: column; gap: 22px; max-width: 760px; }
.toast { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); z-index: 30; display: none; background: var(--btn-bg); color: var(--btn-fg); padding: 12px 18px; border-radius: 999px; font-size: 14px; box-shadow: 0 10px 30px var(--shadow); max-width: calc(100vw - 32px); }
.spin { display: inline-block; width: 11px; height: 11px; border-radius: 50%; border: 2px solid var(--rule); border-top-color: var(--ink); animation: spin .8s linear infinite; vertical-align: -1px; margin-right: 6px; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  body, .popover, .deck > .receipt { transition: none; }
  .spin { animation: none; }
  ::view-transition-group(*), ::view-transition-old(*), ::view-transition-new(*) { animation: none !important; }
}

/* responsive */
@media (max-width: 1100px) {
  .hero-text, .checks { grid-column: 1 / -1; }
  .checks { padding: 32px 0 146px; align-items: center; }
  .stamp { left: calc(50% + 88px); }
  .deck-hint { left: 50%; transform: translateX(-190px); }
  .diary-main, .side { grid-column: 1 / -1; }
  .side { margin-top: 40px; display: grid; grid-template-columns: 1fr 1fr; gap: 40px; }
}
@media (max-width: 900px) {
  .page { padding: 32px 24px; gap: 48px; }
  /* one column: the 12-column gaps alone would be wider than a phone */
  .hero, .three, .diary-wrap { grid-template-columns: minmax(0, 1fr); column-gap: 0; }
  .coins, .key, .margin { grid-column: 1 / -1; }
  .coins { max-width: 360px; margin-bottom: 24px; }
  .margin { padding-left: 0; border-left: 0; margin-top: 28px; }
  .lrow { grid-template-columns: 70px minmax(0, 1fr) 190px 110px 110px; }
  .lrow .leader { display: none; }
}
@media (max-width: 720px) {
  .page { padding: 24px 16px; gap: 44px; }
  .mast-row { gap: 14px; }
  .monthnav { order: 3; width: 100%; justify-content: space-between; }
  .monthnav .current { width: auto; flex: 1; font-size: 20px; }
  .local { display: none; }
  .lede { font-size: 19px; }
  .figures .value { font-size: 24px; }
  .figures > div { padding: 16px 10px 0; }
  .receipt, .deck { width: 320px; }
  .checks { padding-bottom: 108px; }
  .deck-hint { left: 0; transform: none; bottom: 40px; }
  /* On a phone there is no room to deal sideways: spread into a swipeable row */
  .deck.open { width: 100%; height: auto !important; display: flex; gap: 16px; overflow-x: auto; scroll-snap-type: x mandatory; padding: 4px 8px 24px; }
  .deck.open > .receipt { position: relative; flex: none; width: 300px; transform: none; scroll-snap-align: center; }
  .stamp { width: 124px; height: 124px; left: auto; right: 8px; }
  .side { display: flex; }
  h2 { font-size: 28px; }
  .sec-head .hint { margin-left: 0; width: 100%; }
  table.diary, .diary thead, .diary tbody { display: block; }
  .diary thead tr, .diary tbody tr { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); }
  .diary thead th:last-child { display: none; }
  .diary tbody tr { height: auto; }
  .diary tbody td { display: block; height: 60px; }
  .diary tbody td.week { grid-column: 1 / -1; height: auto; width: auto; font-size: 14px; padding: 2px 4px 8px; text-align: right; }
  .diary .d { font-size: 13px; }
  .diary .d small { display: none; }
  .lrow.head { display: none; }
  .lrow { grid-template-columns: minmax(0, 1fr) auto; gap: 6px 12px; padding: 12px 0; }
  .lrow .date { order: 3; grid-column: 1 / -1; font-size: 13px; font-family: var(--mono); color: var(--muted); }
  .lrow .date:empty { display: none; }
  .lrow .who { order: 1; } .lrow .money { order: 2; }
  .lrow .catcell { order: 4; } .lrow .by { order: 5; justify-content: flex-end; }
  .cat, .pills button, .round { min-height: 44px; }
  .drop .status { margin-left: 0; align-items: flex-start; text-align: left; }
}
</style>
</head>
<body>
__BANNER__
<div class="page">
  <header class="mast">
    <div class="mast-row">
      <div class="brand"><span class="title">Expense Tracker</span><span class="label" id="issue"></span></div>
      <nav class="monthnav" aria-label="Month">
        <button type="button" class="round" id="prev" aria-label="Previous month">‹</button>
        <span class="current" id="month-name" aria-live="polite"></span>
        <button type="button" class="round" id="next" aria-label="Next month">›</button>
      </nav>
      <div class="mast-right">
        <span class="local"><span class="dot"></span><span id="local-text"></span></span>
        <button type="button" class="round" id="theme"></button>
        <a class="pill-btn" id="import-btn" href="#ledger">Import a statement</a>
      </div>
    </div>
    <div class="double-rule"></div>
  </header>

  <main id="report" style="display:flex;flex-direction:column;gap:56px">
    <section class="hero" id="hero"></section>
    <section class="block" id="coins-sec"></section>
    <section class="diary-wrap" id="diary-sec"></section>
    <section class="block" id="ledger" aria-label="The ledger">
      <div class="sec-head"><span class="num">§3</span><h2>The ledger</h2><span class="hint" id="ledger-hint"></span></div>
      <div id="intake"></div>
      <div class="pills" id="pills" role="group" aria-label="Filter transactions"></div>
      <div class="ledger" id="rows"></div>
      <div class="ledger-foot" id="ledger-foot">
        <span id="showing"></span>
        <span class="links">
          <button type="button" class="primary" id="see-all"></button>
          <button type="button" id="csv">Export CSV</button>
          <button type="button" id="json">Export JSON</button>
        </span>
      </div>
    </section>
  </main>

  <footer>
    <div class="double-rule flip"></div>
    <div class="row label-sm"><span id="printed"></span><span id="demo-mark"></span></div>
  </footer>
</div>
<div class="popover" id="popover" hidden>
  <div role="listbox" id="listbox" tabindex="-1"></div>
  <hr>
  <label><input type="checkbox" id="remember" checked><span id="remember-text"></span></label>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>

<script>
const DATA = __DATA__;
const EDITABLE = __EDITABLE__;
const DEMO = __DEMO__;
const REPO = "__REPO__";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const cur = DATA.currency;
const num = (v) => Math.abs(v).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
const money = (v) => cur + num(v);
const money0 = (v) => cur + Math.round(Math.abs(v)).toLocaleString("en-US");
const plural = (n, w, p) => `${n} ${n === 1 ? w : (p || w + "s")}`;
const pct = (v) => Math.round(v) + "%";
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const monthName = (m) => MONTHS[+m.slice(5, 7) - 1];
const monthFull = (m) => `${monthName(m)} ${m.slice(0, 4)}`;
const monthShort = (m) => `${monthName(m).slice(0, 3)} ${m.slice(0, 4)}`;
const parseDay = (d) => new Date(d.slice(0, 10) + "T00:00:00");
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// Categories map onto five colour groups; income and "kept" are green
const GROUP_LABEL = {kept: "Kept", housing: "Rent and housing", groceries: "Groceries", bills: "Bills and subscriptions", other: "Everything else", eating: "Eating out"};
const GROUP_ORDER = ["kept", "housing", "groceries", "bills", "other", "eating"];
function group(category) {
  const c = (category || "").toLowerCase();
  if (/hous|rent|mortgage/.test(c)) return "housing";
  if (/grocer/.test(c)) return "groceries";
  if (/eat|dining|restaurant|food|coffee|drink/.test(c)) return "eating";
  if (/electric|gas \(home\)|utilit|internet|phone|subscri|insur|apple|music|gym|bill/.test(c)) return "bills";
  return "other";
}
const color = (g) => `var(--${g === "kept" || g === "income" ? "green" : g})`;

let month = null, filter = "all", showAll = false, uploading = false;
const editedNow = new Set();

// ------------------------------------------------------------------ data
const inMonth = (m) => DATA.transactions.filter((t) => t.month === m);
function stats(m) {
  const txns = inMonth(m);
  const expenses = txns.filter((t) => t.kind === "expense");
  const incomes = txns.filter((t) => t.kind === "income");
  const spent = expenses.reduce((s, t) => s - t.amount, 0);
  const income = incomes.reduce((s, t) => s + t.amount, 0);
  return {txns, expenses, incomes, spent, income, net: income - spent, rate: income > 0 ? 100 * (income - spent) / income : null};
}
const monthIndex = (m) => DATA.months.findIndex((x) => x.month === m);
const priorMonths = (m, n = 6) => DATA.months.slice(Math.max(0, monthIndex(m) - n), Math.max(0, monthIndex(m))).map((x) => x.month);
function byCategory(expenses) {
  const out = {};
  for (const t of expenses) out[t.category || "Uncategorized"] = (out[t.category || "Uncategorized"] || 0) - t.amount;
  return out;
}
function topMerchant(expenses, category) {
  const out = {};
  for (const t of expenses) if (!category || t.category === category) out[t.merchant] = (out[t.merchant] || 0) - t.amount;
  return Object.entries(out).sort((a, b) => b[1] - a[1])[0];
}

// ------------------------------------------------------------------ masthead
function renderMast() {
  const i = monthIndex(month);
  $("issue").textContent = month ? `Monthly report · No. ${i + 1}` : "Monthly report";
  $("month-name").textContent = month ? monthFull(month) : "No statements yet";
  for (const [id, off] of [["prev", i <= 0], ["next", i < 0 || i >= DATA.months.length - 1]]) {
    $(id).disabled = off;
    $(id).setAttribute("aria-disabled", String(off));
  }
  $("local-text").textContent = DEMO ? "Demo · synthetic data" : "Stored on this machine";
  $("printed").textContent = "Printed on this machine · " + DATA.printedAt;
  $("demo-mark").textContent = DEMO ? "Synthetic demo data" : "";
}

// ------------------------------------------------------------------ hero
function receiptFor(s) {
  const txns = DATA.transactions.filter((t) => t.statementId === s.id);
  const inflow = txns.filter((t) => t.amount > 0), outflow = txns.filter((t) => t.amount < 0);
  const inSum = inflow.reduce((a, t) => a + t.amount, 0), outSum = -outflow.reduce((a, t) => a + t.amount, 0);
  const card = s.account === "credit_card";
  const checked = s.opening != null && s.closing != null;
  const expect = checked ? (card ? s.opening + outSum - inSum : s.opening + inSum - outSum) : null;
  const diff = checked ? Math.round((s.closing - expect) * 100) / 100 : null;
  const ok = checked && s.reconciled !== false && Math.abs(diff) < 0.005;
  const acct = {checking: "Checking", savings: "Savings", credit_card: "Credit card"}[s.account] || "Account";
  const line = (a, b, cls = "") => `<div class="line ${cls}"><span>${a}</span><span>${b}</span></div>`;
  const signed = (v) => (v < 0 ? "−" : "") + num(v);
  let body = `<span class="center head">STATEMENT CHECK</span>
    <span class="center note" style="font-size:12px">${esc(s.bank)}<br>${acct} · ${monthShort(s.month)}</span><div class="dash"></div>`;
  if (!checked) {
    body += `<span class="center note">This statement shows no opening or closing balance, so it can't be checked.</span>`;
  } else {
    body += line(card ? "Previous balance" : "Opening balance", signed(s.opening));
    body += card
      ? line(`+ ${plural(outflow.length, "purchase")}`, num(outSum)) + line(`− ${plural(inflow.length, "payment")}`, num(inSum))
      : line(`+ ${plural(inflow.length, "deposit")}`, num(inSum)) + line(`− ${plural(outflow.length, "payment")}`, num(outSum));
    body += `<div class="dash"></div>` + line("We expect", signed(expect)) + line("Bank says", signed(s.closing));
    body += line("Difference", signed(diff), ok ? "total" : "total flag");
    body += `<div class="dash"></div><span class="center note">${plural(txns.length, "transaction")} · ${ok ? "every one accounted for" : "some may be missing or misread"}</span>`;
  }
  let zig = "M0 0 H380 V2";
  for (let x = 370, i = 1; x >= 0; x -= 10, i++) zig += ` L${x} ${i % 2 ? 14 : 2}`;
  return {ok, checked, diff, html: `<div class="receipt"><div class="body">${body}</div>
    <svg viewBox="0 0 380 14" preserveAspectRatio="none" aria-hidden="true"><path d="${zig} Z" fill="var(--paper)"/></svg></div>`};
}

function stamp(state, diff) {
  const when = monthFull(month).toUpperCase();
  const text = state === "ok" ? `RECONCILED · TO THE CENT · ${when} · `
    : state === "bad" ? `CHECK NEEDED · DIFFERENCE ${num(diff)} · ${when} · `
    : `NOT CHECKED · NO BALANCES · ${when} · `;
  const label = state === "ok" ? `Stamp: reconciled to the cent, ${monthFull(month)}`
    : state === "bad" ? `Stamp: check needed, the balances differ by ${money(diff)}`
    : `Stamp: not checked, no statement balances for ${monthFull(month)}`;
  const size = Math.min(13, 372 / (text.length * 0.62));
  const mark = state === "ok" ? `<path d="M68 90 l13 13 l28 -30" fill="none" stroke="var(--stamp)" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>`
    : state === "bad" ? `<text x="88" y="100" text-anchor="middle" font-family="DM Mono, monospace" font-size="34" font-weight="500" fill="var(--stamp)">!</text>`
    : `<text x="88" y="96" text-anchor="middle" font-family="DM Mono, monospace" font-size="22" fill="var(--stamp)">–</text>`;
  return `<svg class="stamp ${state === "none" ? "muted" : ""}" viewBox="0 0 176 176" role="img" aria-label="${esc(label)}">
    <defs><path id="stamp-arc" d="M 88 88 m -60 0 a 60 60 0 1 1 120 0 a 60 60 0 1 1 -120 0"/></defs>
    <circle cx="88" cy="88" r="80" fill="none" stroke="var(--stamp)" stroke-width="4"/>
    <circle cx="88" cy="88" r="46" fill="none" stroke="var(--stamp)" stroke-width="1.5"/>
    <text font-family="DM Mono, monospace" font-size="${size.toFixed(1)}" font-weight="500" fill="var(--stamp)" aria-hidden="true"><textPath href="#stamp-arc" textLength="372" lengthAdjust="spacing">${esc(text)}</textPath></text>
    ${mark}</svg>`;
}

function comparison(m, rate) {
  const prior = priorMonths(m, 24).map((p) => ({m: p, s: stats(p)})).filter((x) => x.s.rate != null);
  if (prior.length < 2 || rate == null) return "";
  const better = [...prior].reverse().find((x) => x.s.rate > rate);
  if (!better) return prior.length >= 3 ? ", your best month on record" : "";
  if (better.m === prior[prior.length - 1].m) return `, down from ${pct(better.s.rate)} in ${monthName(better.m)}`;
  return `, your best month since ${monthName(better.m)}`;
}

function renderHero() {
  const s = stats(month), name = monthName(month);
  const priors = priorMonths(month).map(stats);
  const avgSpent = priors.length ? priors.reduce((a, p) => a + p.spent, 0) / priors.length : null;
  const rated = priors.filter((p) => p.rate != null);
  const avgRate = rated.length ? rated.reduce((a, p) => a + p.rate, 0) / rated.length : null;

  const h1 = s.net >= 0
    ? `${name} kept you <span class="win">${money(s.net)}</span> richer.`
    : `${name} cost you <span class="loss">${money(s.net)}</span> more than came in.`;
  const lede = s.income > 0
    ? `You spent ${money(s.spent)} of the ${money(s.income)} that came in and kept ${pct(Math.max(0, s.rate))} of it${comparison(month, s.rate)}.`
    : `You spent ${money(s.spent)}, and no income was recorded this month.`;
  let spentNote = plural(s.expenses.length, "payment"), spentCls = "";
  if (avgSpent) {
    const d = 100 * (s.spent - avgSpent) / avgSpent;
    spentNote = Math.abs(d) < 1 ? "right on your average" : `${pct(Math.abs(d))} ${d < 0 ? "under" : "over"} your average`;
    spentCls = d < 0 ? "good" : "bad";
  }
  // A statement that fails its check goes on top of the deck, so a problem is never hidden
  const receipts = DATA.statements.filter((x) => x.month === month).map(receiptFor)
    .sort((a, b) => Number(a.checked && !a.ok ? 0 : 1) - Number(b.checked && !b.ok ? 0 : 1));
  const bad = receipts.filter((r) => r.checked && !r.ok);
  const state = !receipts.some((r) => r.checked) ? "none" : bad.length ? "bad" : "ok";
  const diff = bad.reduce((a, r) => a + Math.abs(r.diff), 0);
  const noStatement = !receipts.length
    ? `<div class="receipt"><div class="body"><span class="center head">NO STATEMENT YET</span><div class="dash"></div><span class="center note">These figures come from email alerts. Import this month's statement to check them against the bank's balances.</span></div></div>` : "";

  $("hero").setAttribute("aria-label", `${name} in one line`);
  $("hero").innerHTML = `<div class="hero-text">
      <span class="label">${esc(name)}, in one line</span>
      <h1>${h1}</h1>
      <p class="lede">${lede}</p>
      <div class="figures">
        <div><span class="label-sm">Came in</span><span class="value">${money(s.income)}</span><span class="sub">${plural(s.incomes.length, "deposit")}</span></div>
        <div><span class="label-sm">Went out</span><span class="value">${money(s.spent)}</span><span class="sub ${spentCls}">${spentNote}</span></div>
        <div><span class="label-sm">Kept</span><span class="value ${s.net >= 0 ? "good" : "bad"}">${s.rate == null ? "–" : pct(s.rate)}</span><span class="sub">${avgRate == null ? "" : "average " + pct(avgRate)}</span></div>
      </div>
    </div>
    <div class="checks">${deck(receipts.map((r) => r.html), noStatement)}${stamp(state, diff)}</div>`;
  layoutDeck();
}

function deck(cards, fallback) {
  if (!cards.length) return `<div class="deck single">${fallback}</div>`;
  if (cards.length === 1) return `<div class="deck single">${cards[0]}</div>`;
  // The top card comes last in the DOM so it paints over the others
  return `<div class="deck" id="deck" role="button" tabindex="0" aria-expanded="false"
      aria-label="${cards.length} statement checks, stacked. Press to spread them out.">${[...cards].reverse().join("")}</div>
    <span class="deck-hint" id="deck-hint" aria-hidden="true">${cards.length} statements · click to spread</span>`;
}

const TILT = [1.6, -2.2, 3, -1.4, 2.4];
function layoutDeck() {
  const el = $("deck");
  if (!el) return;
  const cards = [...el.children].reverse();  // cards[0] is the top card
  const width = el.offsetWidth;
  const page = document.querySelector(".page");
  const pageLeft = page.getBoundingClientRect().left + parseFloat(getComputedStyle(page).paddingLeft);
  const room = Math.max(0, el.getBoundingClientRect().left - pageLeft);
  // Deal to the left, side by side when there's room, evenly overlapped when there isn't
  const step = Math.min(width + 28, room / Math.max(1, cards.length - 1));
  cards.forEach((c, i) => {
    c.style.zIndex = String(cards.length - i);
    c.style.setProperty("--rest", `translate(${-i * 5}px, ${-i * 5}px) rotate(${TILT[i % TILT.length]}deg)`);
    c.style.setProperty("--peek", `translate(${-i * 26}px, ${-i * 10}px) rotate(${1.6 - i * 4}deg)`);
    c.style.setProperty("--spread", `translate(${-i * step}px, 0) rotate(${i % 2 ? -0.8 : 0.8}deg)`);
  });
  el.style.height = Math.max(...cards.map((c) => c.offsetHeight)) + "px";
}

function toggleDeck(open) {
  const el = $("deck");
  if (!el) return;
  const next = open ?? !el.classList.contains("open");
  const n = el.children.length;
  el.classList.toggle("open", next);
  el.setAttribute("aria-expanded", String(next));
  el.setAttribute("aria-label", `${n} statement checks, ${next ? "spread out. Press to stack them" : "stacked. Press to spread them out"}.`);
  $("deck-hint").textContent = `${n} statements · click to ${next ? "stack" : "spread"}`;
}

// ------------------------------------------------------------------ §1 coins
function largestRemainder(items, total) {
  const raw = items.map((x) => ({...x, exact: total ? 100 * x.amount / total : 0}));
  raw.forEach((x) => (x.coins = Math.floor(x.exact)));
  let left = 100 - raw.reduce((a, x) => a + x.coins, 0);
  [...raw].sort((a, b) => (b.exact - b.coins) - (a.exact - a.coins)).forEach((x) => { if (left > 0) { x.coins++; left--; } });
  return raw;
}

function notes(s) {
  const out = [];
  const cats = byCategory(s.expenses);
  const priors = priorMonths(month).map((m) => byCategory(stats(m).expenses));
  const used = new Set();
  if (priors.length >= 2) {
    let best = null;
    for (const [c, amt] of Object.entries(cats)) {
      const avg = priors.reduce((a, p) => a + (p[c] || 0), 0) / priors.length;
      if (avg < 20) continue;
      const d = 100 * (amt - avg) / avg;
      if (Math.abs(amt - avg) < 25 || Math.abs(d) < 15) continue;  // skip trivial changes
      if (!best || Math.abs(amt - avg) > Math.abs(best.amt - best.avg)) best = {c, amt, avg, d};
    }
    if (best) {
      used.add(best.c);
      out.push({g: group(best.c), text: `${best.c} came to ${money(best.amt)}, ${pct(Math.abs(best.d))} ${best.d < 0 ? "under" : "over"} your ${priors.length}-month average.`});
    }
  }
  const biggest = [...s.expenses].sort((a, b) => a.amount - b.amount)[0];
  if (biggest && s.spent > 0) {
    const share = 100 * -biggest.amount / s.spent;
    if (share >= 5) out.push({g: group(biggest.category), text: `${biggest.merchant} was ${pct(share)} of everything you spent.`});
  }
  const prev = priorMonths(month, 1)[0];
  if (prev) {
    const p = byCategory(stats(prev).expenses);
    let rise = null;
    for (const [c, amt] of Object.entries(cats)) {
      if (used.has(c) || !p[c] || p[c] < 20) continue;
      const d = 100 * (amt - p[c]) / p[c];
      if (amt - p[c] >= 25 && d >= 15 && (!rise || amt - p[c] > rise.up)) rise = {c, d, up: amt - p[c]};
    }
    if (rise) {
      const top = topMerchant(s.expenses, rise.c);
      out.push({g: group(rise.c), text: `${rise.c} rose ${pct(rise.d)} on ${monthName(prev)}${top ? `, mostly at ${top[0]}` : ""}.`});
    }
  }
  return out;
}

function renderCoins() {
  const s = stats(month);
  const fromIncome = s.income > 0 && s.spent <= s.income;
  const base = fromIncome ? s.income : s.spent;
  const sums = {kept: fromIncome ? s.income - s.spent : 0, housing: 0, groceries: 0, bills: 0, other: 0, eating: 0};
  for (const t of s.expenses) sums[group(t.category)] -= t.amount;
  const items = largestRemainder(GROUP_ORDER.map((g) => ({g, amount: sums[g]})).filter((x) => x.amount > 0.005), base);
  const coins = items.flatMap((x) => Array(x.coins).fill(x.g));
  const romans = ["i.", "ii.", "iii."];
  const margin = notes(s);
  $("coins-sec").setAttribute("aria-label", fromIncome ? `Every ${cur}100 that came in` : "Where the money went");
  $("coins-sec").innerHTML = `<div class="sec-head"><span class="num">§1</span>
      <h2>${fromIncome ? `Every ${cur}100 that came in` : "Where the money went"}</h2>
      <span class="hint">${fromIncome ? "Each coin is one dollar in a hundred" : "Each coin is one dollar in every hundred spent"}</span></div>
    <div class="three">
      <div class="coins" aria-hidden="true">${coins.map((g) => `<span style="background:${color(g)}"></span>`).join("")}</div>
      <div class="key">${items.map((x) => `<div class="key-row"><span class="swatch" style="background:${color(x.g)}"></span>
        <span class="n">${cur}${x.coins}</span><span>${GROUP_LABEL[x.g]}</span><span class="amt">${money(x.amount)}</span></div>`).join("")}</div>
      <aside class="margin" aria-label="Notes"><span class="label-sm">In the margin</span>
        ${margin.length ? margin.map((n, i) => `<div class="item"><span class="roman" style="color:${color(n.g)}">${romans[i]}</span><p>${esc(n.text)}</p></div>`).join("")
          : `<p class="muted">Notes appear once there's a month or two of history to compare against.</p>`}
      </aside>
    </div>`;
}

// ------------------------------------------------------------------ §2 diary
const isDay = (d) => /^\d{4}-\d{2}-\d{2}$/.test(d || "");
const shortDate = (key) => { const d = parseDay(key); return `${MONTHS[d.getMonth()].slice(0, 3)} ${d.getDate()}`; };
function dayRange(a, b) {
  const x = parseDay(a), y = parseDay(b);
  if (a === b) return shortDate(a);
  return x.getMonth() === y.getMonth() ? `${shortDate(a)}–${y.getDate()}` : `${shortDate(a)} – ${shortDate(b)}`;
}

// One calendar table, Monday first. ctx carries the day totals and sizing shared by every table.
// A day's dot, drawn as SVG at a whole-pixel size and position so its edge stays crisp.
// Size means amount; a ring marks a day far bigger than the month's usual.
function dotSvg(size, ring, cls = "dot", tint = "") {
  const px = Math.max(6, Math.round(size / 2) * 2), r = px / 2;
  const css = (cls === "dot" ? `margin:${-r}px 0 0 ${-r}px;` : "") + (tint ? `color:${tint};` : "");
  const style = css ? ` style="${css}"` : "";
  const shape = ring
    ? `<circle cx="${r}" cy="${r}" r="${r - 6}" fill="currentColor"/><circle cx="${r}" cy="${r}" r="${r - 1.5}" fill="none" stroke="currentColor" stroke-width="1.5"/>`
    : `<circle cx="${r}" cy="${r}" r="${r}" fill="currentColor"/>`;
  return `<svg class="${cls}" width="${px}" height="${px}" viewBox="0 0 ${px} ${px}" shape-rendering="geometricPrecision" aria-hidden="true"${style}>${shape}</svg>`;
}

function diaryTable(start, end, ctx, caption, spill) {
  const gridStart = new Date(start);
  gridStart.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  let rows = "";
  for (let w = new Date(gridStart); w <= end; w.setDate(w.getDate() + 7)) {
    let cells = "", total = 0;
    const weekDays = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(w); d.setDate(w.getDate() + i);
      const we = i >= 5 ? "we" : "";
      if (d < start || d > end) { cells += `<td class="${we}"></td>`; continue; }
      const key = iso(d), amt = ctx.perDay[key] || 0;
      const monthTag = spill && (+d === +start || d.getDate() === 1) ? `<small>${MONTHS[d.getMonth()].slice(0, 3)}</small>` : "";
      const pending = ctx.pending(key);
      if (pending) {
        cells += `<td class="${we} pending"><span class="d" aria-hidden="true">${d.getDate()}</span>
          <span class="sr-only">${shortDate(key)}: ${pending}</span></td>`;
        continue;
      }
      total += amt;
      weekDays.push(key);
      const outlier = amt > 3 * ctx.median && amt > 500;
      const size = amt <= 0 ? 0 : outlier ? ctx.big : Math.min(ctx.cap, 6 + 3 * Math.sqrt(amt));
      const inner = `<span class="d" aria-hidden="true">${d.getDate()}${monthTag}</span>
        ${size ? dotSvg(size, outlier, "dot", ctx.tint(key)) : ""}`;
      const said = `${WD[d.getDay()]} ${shortDate(key)}: ${amt ? `${money(amt)}, mostly ${ctx.topCat[key]}` : "nothing spent"}`;
      cells += `<td class="${we}${picked.has(key) ? " sel" : ""}"><button type="button" class="day" data-day="${key}" aria-pressed="${picked.has(key)}"
            aria-label="${said}">${inner}</button></td>`;
    }
    rows += `<tr>${cells}<td class="week">${weekDays.length
      ? `<button type="button" class="wk" data-days="${weekDays.join(",")}" aria-label="${total ? money0(total) + " spent this week" : "Nothing spent this week"}. Select the week's days">${total ? money0(total) : "–"}</button>`
      : ""}</td></tr>`;
  }
  return `<table class="diary${spill ? " spill-table" : ""}"><caption class="sr-only">${esc(caption)}</caption>
    <thead><tr><th>MON</th><th>TUE</th><th>WED</th><th>THU</th><th>FRI</th><th>SAT</th><th>SUN</th><th>WEEK</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function renderDiary() {
  const s = stats(month), name = monthName(month);
  const small = matchMedia("(max-width: 720px)").matches;
  // The diary is a real calendar: every payment dated in this month, whichever
  // statement it came on. A statement's days in a month you can't navigate to
  // (e.g. Dec 11-31 on your first January statement) are listed after it.
  const y = +month.slice(0, 4), mo = +month.slice(5, 7);
  const monthStart = new Date(y, mo - 1, 1), monthEnd = new Date(y, mo, 0);
  const firstKey = iso(monthStart), lastKey = iso(monthEnd);
  const known = new Set(DATA.months.map((x) => x.month));
  const inCalendar = DATA.transactions.filter((t) => t.kind === "expense" && t.date.slice(0, 7) === month);
  const strays = s.expenses.filter((t) => isDay(t.date.slice(0, 10)) && t.date.slice(0, 7) !== month && !known.has(t.date.slice(0, 7)));
  diaryExpenses = [...inCalendar, ...strays];

  const perDay = {}, biggestOn = {};
  for (const t of diaryExpenses) {
    const d = t.date.slice(0, 10);
    if (!isDay(d)) continue;
    perDay[d] = (perDay[d] || 0) - t.amount;
    if (!biggestOn[d] || t.amount < biggestOn[d].amount) biggestOn[d] = t;
  }
  const vals = Object.values(perDay).filter((v) => v > 0).sort((a, b) => a - b);
  const median = vals.length ? vals[Math.floor((vals.length - 1) / 2)] : 0;

  // A day with nothing on it is only "empty" if some imported statement covers it
  const periods = DATA.statements.filter((x) => isDay(x.periodStart) && isDay(x.periodEnd));
  const covered = (key) => periods.some((x) => x.periodStart <= key && key <= x.periodEnd);
  const lastCovered = periods.length ? periods.map((x) => x.periodEnd).sort().at(-1) : null;
  const firstCovered = periods.length ? periods.map((x) => x.periodStart).sort()[0] : null;
  const pending = (key) =>
    perDay[key] || !periods.length || covered(key) ? ""
    : key > lastCovered ? "not on an imported statement yet"
    : "no imported statement covers this day";
  // Each dot takes the colour of the category the day's money mostly went to (the §1 key)
  const byCat = {};
  for (const t of diaryExpenses) {
    const d = t.date.slice(0, 10), c = t.category || "Uncategorized";
    (byCat[d] ||= {})[c] = (byCat[d][c] || 0) - t.amount;
  }
  const topCat = Object.fromEntries(Object.entries(byCat).map(([d, cats]) => [d, Object.entries(cats).sort((a, b) => b[1] - a[1])[0][0]]));
  const tint = (key) => (topCat[key] === "Uncategorized" ? "var(--stamp)" : color(group(topCat[key])));
  const ctx = {perDay, biggestOn, median, cap: small ? 24 : 44, big: small ? 30 : 56, pending, topCat, tint};

  let notes = "";
  if (lastCovered && lastCovered >= firstKey && lastCovered < lastKey) notes += `Days after ${shortDate(lastCovered)} aren't on an imported statement yet. `;
  if (firstCovered && firstCovered > firstKey && firstCovered <= lastKey) notes += `Days before ${shortDate(firstCovered)} come from a statement you haven't imported.`;

  const spills = [
    ["Earlier days on this statement", Object.keys(perDay).filter((k) => k < firstKey).sort()],
    ["Later days on this statement", Object.keys(perDay).filter((k) => k > lastKey).sort()],
  ].filter(([, keys]) => keys.length).map(([title, keys]) => {
    const total = keys.reduce((a, k) => a + perDay[k], 0);
    const noPending = {...ctx, pending: () => ""};
    return `<details class="spill"><summary><span class="spill-title">${title}</span>
        <span class="muted">${dayRange(keys[0], keys.at(-1))} · ${money0(total)} over ${plural(keys.length, "day")}</span>
        <span class="spill-open" aria-hidden="true"></span></summary>
      ${diaryTable(parseDay(keys[0]), parseDay(keys.at(-1)), noPending, `${title}: daily spending ${dayRange(keys[0], keys.at(-1))}`, true)}</details>`;
  }).join("");

  const legend = `<div class="diary-legend" aria-hidden="true">
      <span>${dotSvg(16, false, "key", "var(--muted)")}${cur}10</span><span>${dotSvg(28, false, "key", "var(--muted)")}${cur}50</span><span>${dotSvg(44, false, "key", "var(--muted)")}${cur}150+</span>
      <span>${dotSvg(40, true, "key", "var(--muted)")}far more than a usual day</span>
      <span class="legend-colours">Colour is where the day's money mostly went:
        ${["housing", "groceries", "bills", "eating", "other"].map((g) => `<i style="background:${color(g)}"></i>${GROUP_LABEL[g].replace("Rent and housing", "Housing").replace("Bills and subscriptions", "Bills")}`).join(" ")}</span></div>`;

  const rule = s.expenses.filter((t) => t.categorySource === "rule" || t.categorySource === "user").length;
  const ai = s.expenses.filter((t) => t.categorySource === "ai").length;
  const waiting = s.expenses.filter((t) => !t.category).length;
  const payees = {};
  for (const t of s.expenses) payees[t.merchant] = (payees[t.merchant] || 0) - t.amount;
  const top = Object.entries(payees).sort((a, b) => b[1] - a[1]).slice(0, 5);

  $("diary-sec").setAttribute("aria-label", "The diary");
  $("diary-sec").innerHTML = `<div class="diary-main">
      <div class="sec-head"><span class="num">§2</span><h2>The diary</h2><span class="hint">Every day of ${esc(name)}, from all your statements</span></div>
      ${diaryTable(monthStart, monthEnd, ctx, `Daily spending in ${monthFull(month)}, with weekly totals`, false)}
      ${legend}
      ${notes ? `<p class="diary-note">${esc(notes.trim())}</p>` : ""}
      <p class="pick-hint">Click a day, or drag across several, to see what you spent. Shift-click selects a range; a week's total selects the week.</p>
      ${spills}
    </div>
    <div class="side">
      <section class="picked" id="picked" aria-label="Selected days" hidden></section>
      <div style="display:flex;flex-direction:column;gap:18px">
        <h3>How ${esc(name)} was sorted</h3>
        <div class="tally-row"><div class="top"><span>By saved rules</span><span class="mono">${rule}</span></div><div class="tally" style="color:var(--ink)">${tally(rule)}</div></div>
        <div class="tally-row"><div class="top"><span>By Claude, for new merchants</span><span class="mono">${ai}</span></div><div class="tally" style="color:var(--claude)">${tally(ai)}</div></div>
        <div class="tally-row"><div class="top ${waiting ? "bad" : "muted"}"><span>Waiting for you to check</span><span class="mono">${waiting || "none"}</span></div></div>
        <p class="side-note">Fix a category once and it becomes a rule. Next month, those merchants cost nothing to sort.</p>
      </div>
      <div style="display:flex;flex-direction:column;gap:4px">
        <h3 style="margin-bottom:8px">Who you paid most</h3>
        ${top.map(([n, v], i) => `<div class="payee"><span class="rank">${i + 1}</span><span class="name">${esc(n)}</span><span class="leader"></span><span class="amt">${num(v)}</span></div>`).join("") || '<p class="muted">No payments this month.</p>'}
      </div>
    </div>`;
}

// ---- picking days in the diary
let diaryExpenses = [];
let sheetOpen = false;
const picked = new Set();
let pickAnchor = null, drag = null;

const dayButtons = () => [...document.querySelectorAll("#diary-sec button.day")];
function daysBetween(a, b) {
  const [lo, hi] = [a, b].sort();
  return [...new Set(dayButtons().map((x) => x.dataset.day))].filter((k) => k >= lo && k <= hi);
}

// Draw a selection (the committed one, or a preview while dragging)
function paint(sel) {
  dayButtons().forEach((b) => {
    const on = sel.has(b.dataset.day);
    b.setAttribute("aria-pressed", String(on));
    b.closest("td").classList.toggle("sel", on);
  });
  document.querySelectorAll("#diary-sec table.diary tbody tr").forEach((tr) => {
    const tds = [...tr.children].slice(0, 7);
    tds.forEach((td, i) => {
      const on = td.classList.contains("sel");
      td.classList.toggle("jl", on && !!tds[i - 1]?.classList.contains("sel"));
      td.classList.toggle("jr", on && !!tds[i + 1]?.classList.contains("sel"));
    });
  });
}

function pickDays(keys, on) {
  keys.forEach((k) => (on ? picked.add(k) : picked.delete(k)));
  paint(picked);
  renderPicked();
}

function renderPicked() {
  const el = $("picked");
  if (!el) return;
  const side = el.closest(".side");
  if (!picked.size) {
    el.hidden = true;
    side.classList.remove("picking");
    sheetOpen = false;
    document.documentElement.classList.remove("sheet-open");
    return;
  }
  const days = [...picked].sort();
  const txns = diaryExpenses.filter((t) => picked.has(t.date.slice(0, 10)));
  const total = txns.reduce((a, t) => a - t.amount, 0);
  const quiet = days.filter((day) => !txns.some((t) => t.date.slice(0, 10) === day));
  const groups = days.filter((day) => !quiet.includes(day)).map((day) => {
    const list = txns.filter((t) => t.date.slice(0, 10) === day).sort((a, b) => a.amount - b.amount);
    const sum = list.reduce((a, t) => a - t.amount, 0);
    const d = parseDay(day);
    return `<div class="pick-day"><div class="pick-date"><span>${WD[d.getDay()]} ${shortDate(day)}</span><span class="mono">${num(sum)}</span></div>
      ${list.map((t) => `<div class="pick-row"><span class="cdot" style="background:${t.category ? color(group(t.category)) : "var(--stamp)"}"></span>
        <span class="pick-name">${esc(t.merchant)}<small>${esc(t.category || "Needs a look")}</small></span><span class="mono">−${num(t.amount)}</span></div>`).join("")}</div>`;
  }).join("");
  const none = quiet.length
    ? `<div class="pick-none">Nothing spent on ${quiet.map((k, i) => (i === 0 || k.slice(0, 7) !== quiet[i - 1].slice(0, 7) ? shortDate(k) : parseDay(k).getDate())).join(", ")}</div>` : "";
  el.innerHTML = `<div class="pick-top"><div><span class="label-sm">Selected days</span>
        <div class="pick-total">${money(total)}</div>
        <div class="pick-sub">${plural(days.length, "day")} · ${plural(txns.length, "payment")}${quiet.length ? ` · ${quiet.length} with no spending` : ""}</div></div>
      <span class="pick-actions"><button type="button" class="pick-more" id="pick-more" aria-expanded="${sheetOpen}">${sheetOpen ? "Hide list" : "Show list"}</button>
        <button type="button" class="pick-clear" id="pick-clear">Clear</button></span></div>
    <div class="pick-scroll">${groups}${none}</div>`;
  el.hidden = false;
  side.classList.add("picking");
  // Beside the calendar the list never grows the page: it's capped at the calendar's height
  const wide = !matchMedia("(max-width: 1100px)").matches;
  const cal = document.querySelector(".diary-main");
  el.style.maxHeight = wide ? Math.min(innerHeight - 32, cal ? cal.offsetHeight : 600) + "px" : "";
  // As a bottom sheet it starts as a slim bar; the page gets that much room at the end so
  // no day can be stuck underneath it
  el.classList.toggle("expanded", !wide && sheetOpen);
  document.documentElement.classList.toggle("sheet-open", !wide);
  if (!wide) {
    const bar = el.querySelector(".pick-top").offsetHeight;
    document.documentElement.style.setProperty("--sheet", bar + 28 + "px");
    // Bringing a day into view puts it above the sheet, whatever its current height
    document.documentElement.style.setProperty("--sheet-view", el.offsetHeight + 28 + "px");
  }
}

// Click toggles, Shift-click picks a range, dragging across days selects (or clears) the span.
// Pointer events handle mouse, pen and touch; keyboard presses come through as plain clicks.
// The day under the pointer; between cells, on the week column or past the calendar's
// edge, the nearest day in the calendar the drag started in, so a drag never "drops".
function dayAt(x, y, table) {
  const hit = document.elementFromPoint(x, y)?.closest?.("#diary-sec button.day");
  if (hit && hit.closest("table") === table) return hit;
  // Well above or below the calendar: hold the last day rather than jump rows
  const body = table.tBodies[0].getBoundingClientRect();
  if (y < body.top - 24 || y > body.bottom + 24) return null;
  let best = null, bestDist = Infinity;
  for (const b of table.querySelectorAll("button.day")) {
    const r = b.getBoundingClientRect();
    const dx = Math.max(r.left - x, 0, x - r.right), dy = Math.max(r.top - y, 0, y - r.bottom);
    if (dx * dx + dy * dy < bestDist) { bestDist = dx * dx + dy * dy; best = b; }
  }
  return best;
}

function dragTo(x, y) {
  const b = dayAt(x, y, drag.table);
  if (!b || b.dataset.day === drag.last) return;
  drag.last = b.dataset.day;
  drag.moved = true;
  const next = new Set(picked);
  daysBetween(drag.start, drag.last).forEach((k) => (drag.mode === "add" ? next.add(k) : next.delete(k)));
  drag.preview = next;
  paint(next);
}

// Scroll the page while the pointer is held near the top or bottom edge
function autoScroll() {
  if (!drag || drag.touch) return;
  const edge = 56, y = drag.y;
  const body = drag.table.tBodies[0].getBoundingClientRect();
  // Only scroll while part of the calendar is still out of view in that direction
  const dy = y < edge && body.top < 0 ? -Math.ceil((edge - y) / 3)
    : y > innerHeight - edge && body.bottom > innerHeight ? Math.ceil((y - innerHeight + edge) / 3) : 0;
  if (dy) { scrollBy(0, dy); dragTo(drag.x, drag.y); }
  drag.raf = requestAnimationFrame(autoScroll);
}

function endDrag() {
  if (!drag) return null;
  const d = drag;
  drag = null;
  cancelAnimationFrame(d.raf);
  document.documentElement.classList.remove("dragging");
  return d;
}

$("diary-sec").addEventListener("pointerdown", (e) => {
  const b = e.target.closest("button.day");
  if (!b || e.button !== 0) return;
  const key = b.dataset.day;
  if (sheetOpen) { sheetOpen = false; renderPicked(); }
  drag = {start: key, last: key, moved: false, shift: e.shiftKey, touch: e.pointerType === "touch",
    mode: picked.has(key) ? "remove" : "add", preview: null, table: b.closest("table"), x: e.clientX, y: e.clientY};
  if (!drag.touch) {
    e.preventDefault();  // no text selection or native drag while painting days
    try { b.setPointerCapture(e.pointerId); } catch (err) {}
    document.documentElement.classList.add("dragging");
    drag.raf = requestAnimationFrame(autoScroll);
  }
});
document.addEventListener("pointermove", (e) => {
  if (!drag || drag.touch) return;
  drag.x = e.clientX; drag.y = e.clientY;
  dragTo(e.clientX, e.clientY);
});
document.addEventListener("pointerup", () => {
  const d = endDrag();
  if (!d) return;
  if (d.moved) {
    picked.clear();
    d.preview.forEach((k) => picked.add(k));
    pickAnchor = d.last;
    paint(picked);
    renderPicked();
  } else if (d.shift && pickAnchor) {
    pickDays(daysBetween(pickAnchor, d.start), true);
    pickAnchor = d.start;
  } else {
    pickDays([d.start], !picked.has(d.start));
    pickAnchor = d.start;
  }
  suppressClick = true;
  setTimeout(() => (suppressClick = false), 0);
});
document.addEventListener("pointercancel", () => { if (endDrag()) paint(picked); });
let suppressClick = false;

$("diary-sec").addEventListener("click", (e) => {
  const wk = e.target.closest("button.wk");
  if (wk) {
    const keys = wk.dataset.days.split(",").filter(Boolean);
    pickDays(keys, !keys.every((k) => picked.has(k)));
    return;
  }
  const b = e.target.closest("button.day");
  if (!b || suppressClick) return;
  // Keyboard (Enter/Space) arrives as a click with no pointer sequence
  const key = b.dataset.day;
  if (e.shiftKey && pickAnchor) pickDays(daysBetween(pickAnchor, key), true);
  else pickDays([key], !picked.has(key));
  pickAnchor = key;
});
$("diary-sec").addEventListener("click", (e) => {
  if (e.target.closest("#pick-clear")) { pickAnchor = null; pickDays([...picked], false); }
  if (e.target.closest("#pick-more")) { sheetOpen = !sheetOpen; renderPicked(); }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && picked.size && !picking) { pickAnchor = null; pickDays([...picked], false); }
});

function tally(n) {
  let out = "";
  for (let left = n; left > 0; left -= 5) {
    const k = Math.min(5, left);
    const strokes = [4, 10, 16, 22].slice(0, Math.min(k, 4)).map((x) => `M${x} 3V23`).join(" ") + (k === 5 ? " M1 20L28 6" : "");
    out += `<svg width="30" height="26" viewBox="0 0 30 26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="${strokes}"/></svg>`;
  }
  return out;
}

// ------------------------------------------------------------------ §3 ledger
const SPARK = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2l2.2 7.8L22 12l-7.8 2.2L12 22l-2.2-7.8L2 12l7.8-2.2z"/></svg>`;
const CHEVRON = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>`;
const FILTERS = [
  ["all", "All", () => true],
  ["spending", "Spending", (t) => t.kind === "expense"],
  ["income", "Income", (t) => t.kind === "income"],
  ["claude", "Sorted by Claude", (t) => t.kind === "expense" && t.categorySource === "ai"],
  ["review", "Needs a look", (t) => t.kind === "expense" && !t.category],
];

function ledgerRows() {
  return inMonth(month).filter((t) => t.kind !== "transfer").sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id);
}

function renderIntake() {
  if (!EDITABLE) {
    $("intake").innerHTML = `<div class="try" id="try">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 13l2.5-7h11L20 13"/><path d="M4 13v6h16v-6h-4.5l-1.5 2.5h-4L8.5 13z"/></svg>
      <span style="display:flex;flex-direction:column;gap:8px;min-width:0">
        <span style="font:500 21px var(--serif)">${DEMO ? "Try it on your own statements" : "Import more statements"}</span>
        <span>${DEMO ? `<code>pip install git+${REPO}.git</code> <span class="muted">then</span> <code>expense-tracker demo</code>`
          : `<code>expense-tracker serve</code> <span class="muted">to drop in PDFs, or</span> <code>expense-tracker import statement.pdf</code>`}</span>
      </span></div>`;
    return;
  }
  const last = [...DATA.statements].sort((a, b) => (b.importedAt || "").localeCompare(a.importedAt || ""))[0];
  const rows = last ? DATA.transactions.filter((t) => t.statementId === last.id).length : 0;
  const lastText = last ? `<span>Last import: ${esc(last.fileName)} · ${rows} rows · ${last.reconciled === true ? '<span class="good">reconciled</span>' : last.reconciled === false ? '<span class="bad">check needed</span>' : "not checked"}</span>` : "";
  if (!$("drop")) {
    $("intake").innerHTML = `<label class="drop" id="drop">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 13l2.5-7h11L20 13"/><path d="M4 13v6h16v-6h-4.5l-1.5 2.5h-4L8.5 13z"/><path d="M12 3v7M9.5 7.5L12 10l2.5-2.5"/></svg>
      <span style="display:flex;flex-direction:column;gap:4px"><span class="big">Drop a statement PDF here</span>
        <span class="small">or <span class="browse">browse</span> · any bank · stored on this machine</span></span>
      <input type="file" id="file" accept="application/pdf" multiple aria-label="Import statement PDFs">
      <span class="status" id="drop-status" aria-live="polite"></span></label>`;
    wireDrop();
  }
  if (!uploading) $("drop-status").innerHTML = lastText;
}

function renderLedger() {
  $("ledger-hint").textContent = EDITABLE ? "Click a name or a category to change it" : "Newest first";
  renderIntake();
  const all = ledgerRows();
  $("pills").innerHTML = FILTERS.map(([k, label, fn]) => `<button type="button" data-f="${k}" aria-pressed="${filter === k}">${label} ${all.filter(fn).length}</button>`).join("");
  const rows = all.filter(FILTERS.find((f) => f[0] === filter)[2]);
  const shown = showAll ? rows : rows.slice(0, 12);
  let lastDay = null;
  $("rows").innerHTML = `<div class="lrow head" aria-hidden="true"><span>DATE</span><span>PAYEE</span><span></span><span>CATEGORY</span><span>SORTED BY</span><span style="text-align:right">AMOUNT</span></div>` +
    shown.map((t) => {
      const day = t.date.slice(0, 10), d = parseDay(day);
      const dateText = day === lastDay ? "" : isNaN(d) ? esc(day) : `${WD[d.getDay()]} ${d.getDate()}`;
      lastDay = day;
      const expense = t.kind === "expense";
      const g = expense ? group(t.category) : "income";
      const catName = expense ? (t.category || "Needs a look") : t.kind === "income" ? "Income" : "Payment";
      const dot = `<span class="cdot" style="background:${expense && !t.category ? "var(--stamp)" : color(g)}"></span>`;
      const cat = EDITABLE && expense
        ? `<button type="button" class="cat" data-id="${t.id}" aria-haspopup="listbox" aria-expanded="false" aria-label="Category for ${esc(t.merchant)}: ${esc(catName)}. Change">${dot}<span class="cname">${esc(catName)}</span>${CHEVRON}</button>`
        : `<span class="cat" ${EDITABLE ? "" : 'title="Categories can be changed in the app (expense-tracker serve)"'}>${dot}<span class="cname">${esc(catName)}</span></span>`;
      const by = !expense ? `<span class="by">—</span>`
        : t.categorySource === "ai" ? `<span class="by claude">${SPARK}Claude</span>`
        : t.categorySource === "user" ? `<span class="by">${editedNow.has(t.id) ? "You, just now" : "You"}</span>`
        : t.categorySource === "rule" ? `<span class="by">Saved rule</span>`
        : `<span class="by bad">Needs a look</span>`;
      const amount = t.amount > 0 ? `<span class="good">+${num(t.amount)}</span>` : `−${num(t.amount)}`;
      return `<div class="lrow"><span class="date">${dateText}</span>
        <span class="who"><b>${EDITABLE
          ? `<button type="button" class="rename" data-id="${t.id}" aria-label="${esc(t.merchant)}. Rename this merchant"><span class="rn">${esc(t.merchant)}</span>${PENCIL}</button>`
          : esc(t.merchant)}${t.source === "email" ? " · email alert" : ""}</b><small>${esc(t.description)}</small></span>
        <span class="leader" aria-hidden="true"></span><span class="catcell">${cat}</span>${by}<span class="money">${amount}</span></div>`;
    }).join("") + (rows.length ? "" : `<div class="lrow"><span></span><span class="muted">Nothing here this month.</span></div>`);
  $("showing").textContent = `Showing ${shown.length} of ${rows.length}`;
  $("see-all").textContent = showAll ? "Show fewer" : "See every transaction";
  $("see-all").hidden = rows.length <= 12;
}

// ------------------------------------------------------------------ category picker
const pop = $("popover"), listbox = $("listbox");
let picking = null, active = 0;
function openPicker(btn) {
  closePicker(false);
  const t = DATA.transactions.find((x) => String(x.id) === btn.dataset.id);
  picking = {btn, t};
  listbox.setAttribute("aria-label", `Category for ${t.merchant}`);
  listbox.innerHTML = DATA.categories.map((c, i) => `<div class="opt" role="option" id="opt-${i}" data-c="${esc(c)}" aria-selected="${c === t.category}">
    <span class="cdot" style="background:${color(group(c))}"></span>${esc(c)}${c === t.category ? '<span class="tick" aria-hidden="true">✓</span>' : ""}</div>`).join("");
  $("remember-text").textContent = `Always file ${t.merchant} here`;
  $("remember").checked = true;
  pop.hidden = false;
  const r = btn.getBoundingClientRect();
  const left = Math.min(r.left + scrollX, scrollX + document.documentElement.clientWidth - pop.offsetWidth - 12);
  const below = r.bottom + 8 + pop.offsetHeight < innerHeight;
  pop.style.left = Math.max(12, left) + "px";
  pop.style.top = (below ? r.bottom + 8 : r.top - pop.offsetHeight - 8) + scrollY + "px";
  requestAnimationFrame(() => pop.classList.add("open"));
  btn.setAttribute("aria-expanded", "true");
  setActive(Math.max(0, DATA.categories.indexOf(t.category)));
  listbox.focus();
}
function setActive(i) {
  const opts = listbox.querySelectorAll(".opt");
  active = (i + opts.length) % opts.length;
  opts.forEach((o, j) => o.classList.toggle("active", j === active));
  listbox.setAttribute("aria-activedescendant", `opt-${active}`);
  opts[active].scrollIntoView({block: "nearest"});
}
function closePicker(refocus = true) {
  if (!picking) return;
  const btn = picking.btn;
  btn.setAttribute("aria-expanded", "false");
  picking = null;
  pop.classList.remove("open");
  pop.hidden = true;
  if (refocus) btn.focus();
}
async function choose(category) {
  const {t} = picking;
  const remember = $("remember").checked;
  closePicker(false);
  if (category !== t.category) {
    try {
      const res = await fetch(`/api/transactions/${t.id}`, {
        method: "POST", headers: {"Content-Type": "application/json", "X-Expense-Tracker": "1"},
        body: JSON.stringify({category, remember}),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || res.statusText);
      editedNow.add(t.id);
      await reload();
      toast(remember
        ? `${t.merchant} will be filed under ${category} from now on` + (body.alsoUpdated ? ` · ${plural(body.alsoUpdated, "other transaction")} updated` : "")
        : `Filed under ${category}`);
    } catch (err) {
      toast("Couldn't save: " + err.message);
    }
  }
  document.querySelector(`button.cat[data-id="${t.id}"]`)?.focus();
}
// ---- renaming a merchant (web app)
const PENCIL = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>`;
function startRename(btn) {
  const t = DATA.transactions.find((x) => String(x.id) === btn.dataset.id);
  const input = document.createElement("input");
  input.className = "rename-input";
  input.value = t.merchant;
  input.maxLength = 60;
  input.setAttribute("aria-label", `Rename ${t.merchant}. Enter saves, Escape cancels, an empty name undoes your rename`);
  btn.replaceWith(input);
  input.focus();
  input.select();
  let done = false;
  const finish = async (save) => {
    if (done) return;
    done = true;
    const name = input.value.trim();
    if (!save || name === t.merchant) { renderLedger(); document.querySelector(`button.rename[data-id="${t.id}"]`)?.focus(); return; }
    try {
      const res = await fetch(`/api/merchants/${t.id}`, {
        method: "POST", headers: {"Content-Type": "application/json", "X-Expense-Tracker": "1"}, body: JSON.stringify({name}),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || res.statusText);
      await reload();
      toast(name ? `Now shown as ${name} · ${plural(body.transactions, "transaction")}` : "Back to the automatic name");
    } catch (err) {
      renderLedger();
      toast("Couldn't rename: " + err.message);
    }
    document.querySelector(`button.rename[data-id="${t.id}"]`)?.focus();
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); finish(true); }
    else if (e.key === "Escape") { e.preventDefault(); finish(false); }
  });
  input.addEventListener("blur", () => finish(true));
}

if (EDITABLE) {
  $("rows").addEventListener("click", (e) => { const r = e.target.closest("button.rename"); if (r) startRename(r); });
  $("rows").addEventListener("click", (e) => { const b = e.target.closest("button.cat"); if (b) (picking?.btn === b ? closePicker() : openPicker(b)); });
  $("rows").addEventListener("keydown", (e) => {
    const b = e.target.closest("button.cat");
    if (b && (e.key === "ArrowDown" || e.key === "ArrowUp")) { e.preventDefault(); openPicker(b); }
  });
  listbox.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive(active + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(active - 1); }
    else if (e.key === "Home") { e.preventDefault(); setActive(0); }
    else if (e.key === "End") { e.preventDefault(); setActive(-1); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(DATA.categories[active]); }
    else if (e.key === "Escape") { e.preventDefault(); closePicker(); }
  });
  $("remember").addEventListener("keydown", (e) => { if (e.key === "Escape") closePicker(); });
  listbox.addEventListener("click", (e) => { const o = e.target.closest(".opt"); if (o) choose(o.dataset.c); });
  document.addEventListener("mousedown", (e) => { if (picking && !pop.contains(e.target) && !picking.btn.contains(e.target)) closePicker(false); });
  addEventListener("resize", () => closePicker(false));
}

// ------------------------------------------------------------------ upload
function wireDrop() {
  const drop = $("drop");
  // A PDF dropped anywhere else would navigate away from the app
  ["dragover", "drop"].forEach((ev) => document.addEventListener(ev, (e) => e.preventDefault()));
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.add("over")));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove("over")));
  drop.addEventListener("drop", (e) => upload([...e.dataTransfer.files]));
  $("file").addEventListener("change", (e) => { upload([...e.target.files]); e.target.value = ""; });
}
async function upload(files) {
  files = files.filter((f) => f.name.toLowerCase().endsWith(".pdf") || f.type === "application/pdf");
  if (!files.length) { toast("Only PDF statements can be imported."); return; }
  uploading = true;
  const status = $("drop-status");
  const lines = [];
  for (const [n, file] of files.entries()) {
    const started = Date.now();
    const tick = () => {
      const secs = Math.round((Date.now() - started) / 1000);
      status.innerHTML = lines.concat(`<span><span class="spin" aria-hidden="true"></span>${files.length > 1 ? `${n + 1} of ${files.length} · ` : ""}${esc(file.name)} · ${secs < 2 ? "reading" : "extracting and checking"}… ${secs}s</span>`).join("");
    };
    tick();
    const timer = setInterval(tick, 1000);
    try {
      const res = await fetch("/api/import?name=" + encodeURIComponent(file.name), {method: "POST", headers: {"X-Expense-Tracker": "1"}, body: file});
      const body = await res.json().catch(() => ({error: res.statusText}));
      if (!res.ok) throw new Error(body.error);
      const check = body.skipped ? "already imported" : body.reconciled === true ? '<span class="good">reconciled</span>' : body.reconciled === false ? '<span class="bad">check needed</span>' : "not checked";
      lines.push(`<span>${esc(file.name)} · ${body.skipped ? "" : esc(body.message) + " · "}${check}</span>`);
    } catch (err) {
      lines.push(`<span class="bad" role="alert">${esc(file.name)} · ${esc(err.message)}</span>`);
    } finally {
      clearInterval(timer);
      status.innerHTML = lines.join("");
    }
  }
  uploading = false;
  const before = DATA.months.map((m) => m.month).join();
  await reload();
  if (DATA.months.map((m) => m.month).join() !== before && DATA.months.length) go(DATA.months.at(-1).month, false);
  status.innerHTML = lines.join("");
}

// ------------------------------------------------------------------ export
function download(kind) {
  const fields = ["date", "merchant", "description", "category", "amount", "kind", "categorySource", "source"];
  const rows = ledgerRows();
  const text = kind === "json" ? JSON.stringify(rows.map((t) => Object.fromEntries(fields.map((f) => [f, t[f]]))), null, 2)
    : [fields.join(","), ...rows.map((t) => fields.map((f) => `"${String(t[f] ?? "").replace(/"/g, '""')}"`).join(","))].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], {type: kind === "json" ? "application/json" : "text/csv"}));
  a.download = `expense-tracker-${month}.${kind}`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ------------------------------------------------------------------ page
function toast(msg) {
  const t = $("toast");
  t.textContent = msg; t.style.display = "block";
  clearTimeout(toast.timer); toast.timer = setTimeout(() => (t.style.display = "none"), 5000);
}

const SUN = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>`;
const MOON = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>`;
function isDark() {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}
function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t;
  const dark = isDark();
  $("theme").innerHTML = dark ? SUN : MOON;
  $("theme").setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
}
try { applyTheme(localStorage.getItem("et-theme")); } catch (e) { applyTheme(null); }
$("theme").onclick = () => {
  const next = isDark() ? "light" : "dark";
  applyTheme(next);
  try { localStorage.setItem("et-theme", next); } catch (e) {}
};

function render() {
  renderMast();
  const has = DATA.transactions.length > 0 && !!month;
  ["coins-sec", "diary-sec", "pills", "rows", "ledger-foot"].forEach((id) => ($(id).hidden = !has));
  if (!has) {
    $("hero").innerHTML = `<div class="empty-hero" style="grid-column:1/-1"><span class="label">Nothing here yet</span>
      <h1>Drop in a statement, and this becomes your monthly report.</h1>
      <p class="lede">Any bank's PDF works. Every statement is checked against its own opening and closing balance, and your category fixes are remembered.</p></div>`;
    renderIntake();
    return;
  }
  renderHero(); renderCoins(); renderDiary(); paint(picked); renderPicked(); renderLedger();
}

function go(m, animate = true) {
  if (!m) return;
  closePicker(false);
  let done = false;
  const apply = () => {
    if (done) return;
    done = true;
    if (m !== month) { picked.clear(); pickAnchor = null; }
    month = m; showAll = false; filter = "all"; render(); history.replaceState(null, "", "#" + m);
  };
  if (animate && document.startViewTransition && !reduced && document.visibilityState === "visible") {
    document.startViewTransition(apply);
    setTimeout(apply, 250);  // never let a stalled transition block navigation
  } else {
    apply();
  }
}
$("hero").addEventListener("click", (e) => { if (e.target.closest("#deck")) toggleDeck(); });
$("hero").addEventListener("keydown", (e) => {
  if (!e.target.closest("#deck")) return;
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleDeck(); }
  else if (e.key === "Escape") toggleDeck(false);
});
document.addEventListener("click", (e) => { if ($("deck")?.classList.contains("open") && !e.target.closest("#deck")) toggleDeck(false); });
document.fonts?.ready.then(() => month && layoutDeck());
$("prev").onclick = () => go(DATA.months[monthIndex(month) - 1]?.month);
$("next").onclick = () => go(DATA.months[monthIndex(month) + 1]?.month);
$("pills").addEventListener("click", (e) => { const b = e.target.closest("button[data-f]"); if (b) { filter = b.dataset.f; showAll = false; renderLedger(); } });
$("see-all").onclick = () => { showAll = !showAll; renderLedger(); };
$("csv").onclick = () => download("csv");
$("json").onclick = () => download("json");
$("import-btn").onclick = (e) => {
  if (!EDITABLE) return;
  e.preventDefault();
  $("file")?.click();
};
let resizeTimer, wasSmall = matchMedia("(max-width: 720px)").matches;
addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    const small = matchMedia("(max-width: 720px)").matches;
    if (small !== wasSmall && month) { wasSmall = small; renderDiary(); }
    if (month) { paint(picked); renderPicked(); }
    if (month) layoutDeck();
  }, 150);
});

async function reload() {
  Object.assign(DATA, await (await fetch("/api/data")).json());
  if (!DATA.months.some((m) => m.month === month)) month = DATA.months.at(-1)?.month || null;
  render();
}

const fromHash = location.hash.slice(1);
month = DATA.months.some((m) => m.month === fromHash) ? fromHash : (DATA.months.at(-1)?.month || null);
render();
</script>
</body>
</html>
"""
