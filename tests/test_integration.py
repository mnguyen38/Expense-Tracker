"""End-to-end tests: real PDF -> pdfplumber -> parser -> CLI output. No network calls."""

import pytest

fpdf = pytest.importorskip("fpdf")

from expense_tracker.parsers import parse_statement  # noqa: E402

BOA_CHECKING_LINES = [
    "Bank of America",
    "Your Adv Plus Banking - Advantage Checking",
    "March 1, 2026 to March 31, 2026",
    "March 1 - March 31, 2026",
    "Beginning balance on March 1, 2026 $1,000.00",
    "Ending balance on March 31, 2026 $2,338.55",
    "Deposits and other additions",
    "03/02/26 PAYROLL DIRECT DEP ACME ROBOTICS 2,000.00",
    "Total deposits and other additions $2,000.00",
    "Withdrawals and other subtractions",
    "03/05/26 CHECKCARD 0305 TRADER JOES #552 -61.45",
    "03/09/26 Online Banking transfer to SAV 1234 -500.00",
    "03/20/26 STUDENT LOAN SERVICING PAYMENT -100.00",
    "Total withdrawals and other subtractions -$661.45",
]


def _write_pdf(path, lines):
    pdf = fpdf.FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in lines:
        pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))
    return path


@pytest.fixture
def boa_checking_pdf(tmp_path):
    return _write_pdf(tmp_path / "boa_checking.pdf", BOA_CHECKING_LINES)


def test_boa_pdf_parses_and_reconciles(boa_checking_pdf):
    result = parse_statement(boa_checking_pdf)

    assert result["bank_id"] == "boa"
    assert result["statement_type"] == "checking"
    assert len(result["all_transactions"]) == 4
    assert result["opening_balance"] == 1000.00
    assert result["closing_balance"] == 2338.55
    assert result["warnings"] == []  # 1000 + 2000 - 61.45 - 500 - 100 = 2338.55

    # Internal transfer excluded from spending; loan payment tracked as debt
    assert [t["description"] for t in result["expenses"]] == [
        "CHECKCARD 0305 TRADER JOES #552",
        "STUDENT LOAN SERVICING PAYMENT",
    ]
    assert len(result["debt_payments"]) == 1
    assert result["income"][0]["amount"] == 2000.00


def test_boa_pdf_with_misread_line_warns(tmp_path):
    lines = [line for line in BOA_CHECKING_LINES if "TRADER JOES" not in line]
    result = parse_statement(_write_pdf(tmp_path / "boa_missing.pdf", lines))

    assert len(result["warnings"]) == 1
    assert "off by -61.45" in result["warnings"][0]
