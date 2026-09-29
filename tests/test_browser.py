"""
Real-browser tests for the diary's day picking, driven with real mouse, keyboard and touch
input through Playwright. They run against Chrome (or Playwright's Chromium) and are skipped
when neither is available.

    pip install -e ".[dev]"      # includes playwright
    pytest tests/test_browser.py
"""

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from expense_tracker.config import Config  # noqa: E402
from expense_tracker.demo import build_demo  # noqa: E402
from expense_tracker.ledger import Ledger  # noqa: E402
from expense_tracker.report import dashboard_data, render_dashboard  # noqa: E402

DESKTOP = {"width": 1440, "height": 900}
TABLET = {"width": 1000, "height": 800}  # selection list is a bottom sheet here
PHONE = {"width": 390, "height": 844}


@pytest.fixture(scope="module")
def page_file(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("report")
    config = Config(home=tmp)
    with Ledger(":memory:") as ledger:
        build_demo(ledger, config, months=3)
        html = render_dashboard(dashboard_data(ledger, config), demo=True)
    path = tmp / "report.html"
    path.write_text(html, encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        for launch in (lambda: p.chromium.launch(channel="chrome"), lambda: p.chromium.launch()):
            try:
                b = launch()
                break
            except Exception:
                b = None
        if b is None:
            pytest.skip("No Chrome or Playwright Chromium available")
        yield b
        b.close()


class Diary:
    """Drives the diary like a person would: real pointer moves in small steps."""

    def __init__(self, browser, page_file, viewport, touch=False):
        self.ctx = browser.new_context(viewport=viewport, has_touch=touch, is_mobile=touch)
        self.page = self.ctx.new_page()
        self.page.goto(page_file.as_uri())
        self.month = self.page.evaluate("DATA.months.at(-1).month")
        self.last_day = self.page.evaluate(f"new Date({self.month[:4]}, {int(self.month[5:])}, 0).getDate()")

    def close(self):
        self.ctx.close()

    def day(self, n):
        return self.page.locator(
            f'#diary-sec table.diary:not(.spill-table) button.day[data-day="{self.month}-{n:02d}"]'
        )

    def center(self, n):
        self.day(n).scroll_into_view_if_needed()
        box = self.day(n).bounding_box()
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    def drag(self, *days, steps=12):
        """Press on the first day, pass through the others, release on the last."""
        x, y = self.center(days[0])
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        for n in days[1:]:
            box = self.day(n).bounding_box()
            self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps)
        self.page.mouse.up()

    def click(self, n, **kwargs):
        self.day(n).click(**kwargs)

    def selected(self):
        return self.page.evaluate(
            """[...document.querySelectorAll('#diary-sec table.diary:not(.spill-table) button.day[aria-pressed="true"]')]
               .map((b) => +b.dataset.day.slice(8)).sort((a, b) => a - b)"""
        )

    def panel_visible(self):
        return self.page.evaluate("!document.getElementById('picked').hidden")


@pytest.fixture(params=[DESKTOP, TABLET, PHONE], ids=["desktop", "tablet", "phone"])
def diary(request, browser, page_file):
    d = Diary(browser, page_file, request.param)
    yield d
    d.close()


@pytest.fixture
def desktop(browser, page_file):
    d = Diary(browser, page_file, DESKTOP)
    yield d
    d.close()


@pytest.fixture
def tablet(browser, page_file):
    d = Diary(browser, page_file, TABLET)
    yield d
    d.close()


# ---------------------------------------------------------------- clicking


def test_click_toggles_a_day(diary):
    diary.click(5)
    assert diary.selected() == [5]
    assert diary.panel_visible()
    diary.click(5)
    assert diary.selected() == []
    assert not diary.panel_visible()


def test_clicks_add_up(diary):
    for n in (2, 9, 16):
        diary.click(n)
    assert diary.selected() == [2, 9, 16]


# ---------------------------------------------------------------- dragging


def test_drag_forward_selects_the_span(diary):
    diary.drag(3, 8)
    assert diary.selected() == list(range(3, 9))


def test_drag_backward_selects_the_span(diary):
    diary.drag(8, 3)
    assert diary.selected() == list(range(3, 9))


def test_drag_across_weeks(diary):
    diary.drag(1, 20)
    assert diary.selected() == list(range(1, 21))


def test_reported_sequence_unselects_in_one_go(diary):
    """2 -> 1, then 3 -> 6, then dragging from 6 back to 1 must clear all six days."""
    diary.drag(2, 1)
    assert diary.selected() == [1, 2]
    diary.drag(3, 6)
    assert diary.selected() == [1, 2, 3, 4, 5, 6]
    diary.drag(6, 1)
    assert diary.selected() == []


def test_unselect_from_the_middle(diary):
    diary.drag(1, 10)
    diary.drag(4, 7)
    assert diary.selected() == [1, 2, 3, 8, 9, 10]


def test_dragging_back_shrinks_the_span(diary):
    diary.drag(3, 12, 5)
    assert diary.selected() == [3, 4, 5]


def test_dragging_back_past_the_start_flips_direction(diary):
    diary.drag(10, 14, 6)
    assert diary.selected() == list(range(6, 11))


def test_drag_keeps_other_selected_days(diary):
    diary.click(20)
    diary.drag(2, 4)
    assert diary.selected() == [2, 3, 4, 20]


def test_drag_that_returns_to_its_start_toggles_just_that_day(diary):
    diary.drag(5, 9, 5)
    assert diary.selected() == [5]


def test_drag_through_the_week_column_and_past_the_edge(desktop):
    """Overshooting to the right of Sunday, into the week totals, still counts as that week's end."""
    x, y = desktop.center(3)
    table = desktop.page.locator("#diary-sec table.diary:not(.spill-table)").bounding_box()
    desktop.page.mouse.move(x, y)
    desktop.page.mouse.down()
    desktop.page.mouse.move(table["x"] + table["width"] + 80, y, steps=15)  # well past the week column
    desktop.page.mouse.up()
    sunday = desktop.page.evaluate(
        f"""(() => {{ const d = new Date('{desktop.month}-03T00:00'); d.setDate(d.getDate() + (7 - d.getDay()) % 7); return d.getDate(); }})()"""
    )
    assert desktop.selected() == list(range(3, sunday + 1))


def test_release_outside_the_calendar_keeps_the_span(desktop):
    x, y = desktop.center(4)
    desktop.page.mouse.move(x, y)
    desktop.page.mouse.down()
    x2, y2 = desktop.center(6)
    desktop.page.mouse.move(x2, y2, steps=8)
    desktop.page.mouse.move(x2, y2 - 400, steps=8)  # up and out over the page
    desktop.page.mouse.up()
    assert desktop.selected() == [4, 5, 6]  # leaving the calendar holds the last day


def test_sheet_never_blocks_a_drag(tablet):
    """With the bottom sheet open, days behind it can still be reached in one drag."""
    tablet.click(tablet.last_day)
    assert tablet.page.evaluate("getComputedStyle(document.getElementById('picked')).position") == "fixed"
    tablet.drag(1, tablet.last_day - 1)
    assert tablet.selected() == list(range(1, tablet.last_day + 1))


def test_auto_scroll_reaches_days_off_screen(browser, page_file):
    short = Diary(browser, page_file, {"width": 1440, "height": 420})
    try:
        x, y = short.center(1)
        short.page.mouse.move(x, y)
        short.page.mouse.down()
        before = short.page.evaluate("scrollY")
        short.page.mouse.move(x, 415, steps=10)  # hold at the bottom edge
        short.page.wait_for_timeout(1500)
        after = short.page.evaluate("scrollY")
        box = short.day(short.last_day).bounding_box()
        short.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=5)
        short.page.mouse.up()
        assert after > before
        assert short.selected() == list(range(1, short.last_day + 1))
        # it stops once the calendar's last row is in view instead of running to the page end
        assert short.page.evaluate("document.documentElement.scrollHeight - innerHeight - scrollY") > 300
    finally:
        short.close()


# ---------------------------------------------------------------- other ways in


def test_shift_click_selects_a_range(diary):
    diary.click(3)
    diary.click(9, modifiers=["Shift"])
    assert diary.selected() == list(range(3, 10))


def test_week_total_toggles_the_week(desktop):
    week = desktop.page.locator("#diary-sec table.diary:not(.spill-table) button.wk").nth(1)
    days = week.get_attribute("data-days").split(",")
    week.click()
    assert len(desktop.selected()) == len(days)
    week.click()
    assert desktop.selected() == []


def test_keyboard_space_and_enter_toggle(desktop):
    desktop.day(7).focus()
    desktop.page.keyboard.press("Space")
    assert desktop.selected() == [7]
    desktop.page.keyboard.press("Enter")
    assert desktop.selected() == []


def test_escape_clears(diary):
    diary.drag(2, 6)
    diary.page.keyboard.press("Escape")
    assert diary.selected() == []
    assert not diary.panel_visible()


def test_touch_tap_toggles(browser, page_file):
    phone = Diary(browser, page_file, PHONE, touch=True)
    try:
        phone.day(8).scroll_into_view_if_needed()
        phone.day(8).tap()
        assert phone.selected() == [8]
        phone.day(8).tap()
        assert phone.selected() == []
    finally:
        phone.close()


def test_changing_month_clears_the_selection(desktop):
    desktop.drag(2, 5)
    desktop.page.click("#prev")
    desktop.page.wait_for_timeout(400)
    assert desktop.page.evaluate("document.querySelectorAll('#diary-sec td.sel').length") == 0


# ---------------------------------------------------------------- what the panel shows


def test_panel_total_matches_the_payments(desktop):
    desktop.drag(1, 14)
    rows = desktop.page.locator("#picked .pick-row .mono").all_inner_texts()
    head = desktop.page.locator("#picked .pick-total").inner_text()
    assert (
        abs(
            sum(float(r.replace("−", "").replace(",", "")) for r in rows)
            - float(head.strip("$").replace(",", ""))
        )
        < 0.01
    )


def test_zero_spend_days_are_selectable(desktop):
    zero = desktop.page.evaluate(
        """[...document.querySelectorAll('#diary-sec table.diary:not(.spill-table) button.day')]
           .filter((b) => !b.querySelector('svg.dot')).map((b) => +b.dataset.day.slice(8))[0] ?? null"""
    )
    if zero is None:
        pytest.skip("demo month has no zero-spend day")
    desktop.click(zero)
    assert desktop.selected() == [zero]
    assert "Nothing spent on" in desktop.page.locator("#picked").inner_text()


def page_height(d):
    return d.page.evaluate("Math.round(document.documentElement.scrollHeight)")


def test_selection_never_grows_the_page(diary):
    """One day or the whole month: the page is the same height (the list scrolls on its own)."""
    diary.click(1)
    one = page_height(diary)
    diary.drag(2, diary.last_day)
    assert abs(page_height(diary) - one) <= 2


def test_sheet_is_a_slim_bar_until_asked(tablet):
    tablet.drag(1, 12)
    sheet = tablet.page.locator("#picked")
    assert sheet.bounding_box()["height"] < 140
    tablet.page.click("#pick-more")
    assert sheet.bounding_box()["height"] > 200
    assert tablet.page.locator("#picked .pick-day").count() >= 1
    tablet.drag(20, 21)  # working in the calendar tucks the list away again
    assert sheet.bounding_box()["height"] < 140


def test_every_day_stays_reachable_with_the_sheet_open(tablet):
    """Scroll to the very bottom: the last row of the calendar can sit above the bar."""
    tablet.drag(1, tablet.last_day)
    tablet.page.evaluate("scrollTo(0, document.documentElement.scrollHeight)")
    last = tablet.day(tablet.last_day)
    last.scroll_into_view_if_needed()
    box, sheet = last.bounding_box(), tablet.page.locator("#picked").bounding_box()
    assert box["y"] + box["height"] <= sheet["y"] + 1


# ---------------------------------------------------------------- the dots


def test_dots_take_the_colour_of_the_days_top_category(desktop):
    mismatches = desktop.page.evaluate(
        """(() => {
          const bad = [];
          for (const b of document.querySelectorAll('#diary-sec table.diary:not(.spill-table) button.day')) {
            const svg = b.querySelector('svg.dot');
            if (!svg) continue;
            const day = b.dataset.day, sums = {};
            for (const t of diaryExpenses.filter((t) => t.date.slice(0, 10) === day)) sums[t.category] = (sums[t.category] || 0) - t.amount;
            const top = Object.entries(sums).sort((a, b) => b[1] - a[1])[0][0];
            const probe = document.createElement('span');
            probe.style.color = color(group(top));
            document.body.appendChild(probe);
            const want = getComputedStyle(probe).color;
            probe.remove();
            if (getComputedStyle(svg).color !== want) bad.push(day);
          }
          return bad;
        })()"""
    )
    assert mismatches == []


# ---------------------------------------------------------------- renaming in the web app


@pytest.fixture
def app_page(browser, tmp_path):
    """The real web app (editable), served from a demo ledger."""
    import threading
    from http.server import ThreadingHTTPServer

    from expense_tracker.web import make_handler

    config = Config(home=tmp_path)
    with Ledger(config.db_path) as ledger:
        build_demo(ledger, config, months=2)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    ctx = browser.new_context(viewport=DESKTOP)
    page = ctx.new_page()
    page.goto(f"http://127.0.0.1:{httpd.server_address[1]}/")
    yield page
    ctx.close()
    httpd.shutdown()
    httpd.server_close()


def test_rename_a_merchant_inline(app_page):
    first = app_page.locator("#rows button.rename").first
    tid = first.get_attribute("data-id")
    first.click()
    box = app_page.locator("#rows input.rename-input")
    box.fill("Corner Cafe")
    box.press("Enter")
    renamed = app_page.locator(f'#rows button.rename[data-id="{tid}"]')
    renamed.wait_for()
    assert renamed.inner_text().strip() == "Corner Cafe"
    assert renamed.evaluate("(b) => b === document.activeElement")  # focus comes back
    merchant = app_page.evaluate(f"DATA.transactions.find((t) => t.id === {tid}).merchant")
    assert merchant == "Corner Cafe"


def test_escape_cancels_and_empty_undoes_a_rename(app_page):
    first = app_page.locator("#rows button.rename").first
    tid, before = first.get_attribute("data-id"), first.inner_text().strip()
    first.click()
    app_page.locator("#rows input.rename-input").fill("Nope")
    app_page.keyboard.press("Escape")
    assert app_page.locator(f'#rows button.rename[data-id="{tid}"]').inner_text().strip() == before

    app_page.locator(f'#rows button.rename[data-id="{tid}"]').click()
    app_page.locator("#rows input.rename-input").fill("Temporary")
    app_page.keyboard.press("Enter")
    app_page.locator(f'#rows button.rename[data-id="{tid}"]').wait_for()
    app_page.locator(f'#rows button.rename[data-id="{tid}"]').click()
    app_page.locator("#rows input.rename-input").fill("")
    app_page.keyboard.press("Enter")
    app_page.wait_for_function(f"DATA.transactions.find((t) => t.id === {tid}).merchant === {before!r}")
