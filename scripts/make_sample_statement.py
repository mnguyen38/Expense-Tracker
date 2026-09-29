"""
Generate examples/sample_statement.pdf: a synthetic checking statement from a
fictional bank, used for the README demo. Contains no real personal data.

Usage:
    pip install -r requirements-dev.txt
    python scripts/make_sample_statement.py
"""

from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parent.parent / "examples" / "sample_statement.pdf"

OPENING_BALANCE = 3250.00

# (date, description, amount) - negative = money out
TRANSACTIONS = [
    ("03/01/26", "RENT - MAPLE COURT APARTMENTS", -1650.00),
    ("03/02/26", "PAYROLL DEPOSIT - ACME ROBOTICS INC", 2875.40),
    ("03/03/26", "TRADER JOE'S #552 PORTLAND OR", -64.18),
    ("03/04/26", "UBER *TRIP HELP.UBER.COM", -18.72),
    ("03/05/26", "SPOTIFY USA 877-778-1161", -11.99),
    ("03/07/26", "BLUE BOTTLE COFFEE", -6.50),
    ("03/08/26", "PGE ELECTRIC AUTOPAY", -72.35),
    ("03/10/26", "TRANSFER TO SAVINGS XXXX4821", -400.00),
    ("03/11/26", "CHIPOTLE 1187", -13.45),
    ("03/12/26", "APPLE.COM/BILL ICLOUD 200GB", -2.99),
    ("03/14/26", "CVS PHARMACY #8841", -23.10),
    ("03/15/26", "VENMO CASHOUT", 45.00),
    ("03/16/26", "PAYROLL DEPOSIT - ACME ROBOTICS INC", 2875.40),
    ("03/18/26", "COMCAST XFINITY INTERNET", -65.00),
    ("03/20/26", "DELTA AIR LINES 0062", -289.60),
    ("03/22/26", "WHOLE FOODS MKT #10233", -97.84),
    ("03/24/26", "PLANET FITNESS MONTHLY", -24.99),
    ("03/27/26", "AMC THEATRES 2231", -31.50),
    ("03/29/26", "MONTHLY MAINTENANCE FEE", -5.00),
]


def main() -> None:
    closing = round(OPENING_BALANCE + sum(t[2] for t in TRANSACTIONS), 2)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Northwind Community Bank", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for line in [
        "SAMPLE STATEMENT - SYNTHETIC DATA FOR DEMONSTRATION",
        "Everyday Checking  |  Account ending 0000",
        "Jordan Sample, 123 Example Street, Portland, OR 97201",
        "Statement period: March 1, 2026 - March 31, 2026",
        "",
        f"Beginning balance on March 1, 2026: ${OPENING_BALANCE:,.2f}",
        f"Ending balance on March 31, 2026: ${closing:,.2f}",
        "",
    ]:
        pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(25, 7, "Date")
    pdf.cell(125, 7, "Description")
    pdf.cell(35, 7, "Amount", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for date, desc, amount in TRANSACTIONS:
        pdf.cell(25, 6, date)
        pdf.cell(125, 6, desc)
        pdf.cell(35, 6, f"{amount:,.2f}", align="R", new_x="LMARGIN", new_y="NEXT")

    OUT.parent.mkdir(exist_ok=True)
    pdf.output(str(OUT))
    print(f"Wrote {OUT} ({len(TRANSACTIONS)} transactions, closing balance ${closing:,.2f})")


if __name__ == "__main__":
    main()
