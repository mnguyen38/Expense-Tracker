"""Spending threshold notifications via email."""

import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime

# File to track notified thresholds
THRESHOLD_FILE = Path(__file__).parent.parent / "data" / "spending_thresholds.json"


def load_thresholds() -> dict:
    """Load threshold tracking data."""
    if THRESHOLD_FILE.exists():
        with open(THRESHOLD_FILE) as f:
            return json.load(f)
    return {"notified": {}}


def save_thresholds(data: dict):
    """Save threshold tracking data."""
    THRESHOLD_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(THRESHOLD_FILE, "w") as f:
        json.dump(data, f, indent=2)


def send_email(
    to_email: str,
    subject: str,
    message: str,
    smtp_email: str | None = None,
    smtp_password: str | None = None,
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587,
) -> bool:
    """
    Send an email notification.

    Args:
        to_email: Recipient email address
        subject: Email subject
        message: Email body
        smtp_email: Sender email (defaults to SMTP_EMAIL env var)
        smtp_password: Email password/app password (defaults to SMTP_PASSWORD env var)
        smtp_server: SMTP server (default: Gmail)
        smtp_port: SMTP port (default: 587)

    Returns:
        True if sent successfully
    """
    smtp_email = smtp_email or os.environ.get("SMTP_EMAIL")
    smtp_password = smtp_password or os.environ.get("SMTP_PASSWORD")

    if not smtp_email or not smtp_password:
        raise ValueError(
            "SMTP credentials not found. Set SMTP_EMAIL and SMTP_PASSWORD environment variables.\n"
            "For Gmail, use an App Password: https://myaccount.google.com/apppasswords"
        )

    msg = MIMEText(message)
    msg["From"] = smtp_email
    msg["To"] = to_email
    msg["Subject"] = subject

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def check_spending_threshold(
    total_spent: float,
    month: str,
    threshold_interval: float = 1000.0,
    notify_email: str | None = None,
) -> list[float]:
    """
    Check if spending has crossed any threshold and send email notifications.

    Args:
        total_spent: Total spending amount for the month
        month: Month string (e.g., "1/2025")
        threshold_interval: Notify every N dollars spent (default: $1000)
        notify_email: Email address to notify (defaults to NOTIFY_EMAIL env var)

    Returns:
        List of thresholds that were crossed and notified
    """
    notify_email = notify_email or os.environ.get("NOTIFY_EMAIL")

    if not notify_email:
        return []  # Email not configured, skip silently

    # Load tracking data
    data = load_thresholds()
    if month not in data["notified"]:
        data["notified"][month] = []

    # Calculate which thresholds have been crossed
    crossed = []
    threshold = threshold_interval

    while threshold <= total_spent:
        if threshold not in data["notified"][month]:
            crossed.append(threshold)
        threshold += threshold_interval

    # Send notifications for newly crossed thresholds
    notified = []
    for threshold in crossed:
        subject = f"Spending Alert: ${threshold:,.0f} threshold crossed"
        message = f"You've spent ${total_spent:,.0f} in {month}.\n\nThis notification was triggered because your spending crossed the ${threshold:,.0f} threshold."

        try:
            if send_email(notify_email, subject, message):
                data["notified"][month].append(threshold)
                notified.append(threshold)
                print(f"  Email sent: Crossed ${threshold:,.0f} threshold")
        except Exception as e:
            print(f"  Email failed: {e}")

    # Save updated tracking data
    if notified:
        save_thresholds(data)

    return notified


def reset_month_thresholds(month: str):
    """Reset threshold tracking for a specific month."""
    data = load_thresholds()
    if month in data["notified"]:
        del data["notified"][month]
        save_thresholds(data)
        print(f"Reset thresholds for {month}")


# =============================================================================
# Email Templates
# =============================================================================

def _get_spending_html_template() -> str:
    """Return the HTML template for spending summary emails."""
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: #ffffff;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #1a1a1a;
            font-size: 24px;
            margin-bottom: 10px;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }}
        .summary-box {{
            background-color: #f8f9fa;
            border-radius: 6px;
            padding: 20px;
            margin: 20px 0;
        }}
        .total-spent {{
            font-size: 36px;
            font-weight: bold;
            color: #e53935;
        }}
        .total-income {{
            font-size: 24px;
            color: #43a047;
        }}
        .category-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        .category-table th {{
            background-color: #4CAF50;
            color: white;
            padding: 12px;
            text-align: left;
        }}
        .category-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid #eee;
        }}
        .category-table tr:hover {{
            background-color: #f5f5f5;
        }}
        .amount {{
            text-align: right;
            font-family: 'Courier New', monospace;
        }}
        .spending {{
            color: #e53935;
        }}
        .income {{
            color: #43a047;
        }}
        .bar-container {{
            background-color: #eee;
            border-radius: 4px;
            height: 8px;
            width: 100%;
            margin-top: 4px;
        }}
        .bar {{
            background-color: #4CAF50;
            height: 100%;
            border-radius: 4px;
        }}
        .transactions-section {{
            margin-top: 30px;
        }}
        .transaction {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }}
        .transaction-desc {{
            color: #666;
            font-size: 14px;
        }}
        .transaction-date {{
            color: #999;
            font-size: 12px;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 12px;
            color: #999;
            text-align: center;
        }}
        .alert-box {{
            background-color: #fff3e0;
            border-left: 4px solid #ff9800;
            padding: 15px;
            margin: 20px 0;
            border-radius: 0 6px 6px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>

        <div class="summary-box">
            <div>Total Spending</div>
            <div class="total-spent">${total_spent:,.2f}</div>
            {income_section}
        </div>

        {alert_section}

        <h2>Spending by Category</h2>
        <table class="category-table">
            <thead>
                <tr>
                    <th>Category</th>
                    <th class="amount">Amount</th>
                    <th style="width: 100px;"></th>
                </tr>
            </thead>
            <tbody>
                {category_rows}
            </tbody>
        </table>

        {top_transactions_section}

        <div class="footer">
            Generated on {generated_date}<br>
            Expense Tracker
        </div>
    </div>
</body>
</html>
"""


def _get_spending_text_template() -> str:
    """Return the plain text template for spending summary emails."""
    return """
{title}
{'=' * len(title)}

SUMMARY
-------
Total Spending: ${total_spent:,.2f}
{income_line}

{alert_text}

SPENDING BY CATEGORY
--------------------
{category_text}

{top_transactions_text}

---
Generated on {generated_date}
Expense Tracker
"""


def _format_category_rows(by_category: dict, total_spent: float) -> str:
    """Format category data as HTML table rows."""
    if not by_category or total_spent == 0:
        return "<tr><td colspan='3'>No spending data</td></tr>"

    rows = []
    sorted_categories = sorted(by_category.items(), key=lambda x: x[1], reverse=True)

    for category, amount in sorted_categories:
        percentage = (amount / total_spent) * 100 if total_spent > 0 else 0
        row = f"""
            <tr>
                <td>{category}</td>
                <td class="amount spending">-${amount:,.2f}</td>
                <td>
                    <div class="bar-container">
                        <div class="bar" style="width: {percentage:.0f}%;"></div>
                    </div>
                </td>
            </tr>
        """
        rows.append(row)

    return "\n".join(rows)


def _format_category_text(by_category: dict) -> str:
    """Format category data as plain text."""
    if not by_category:
        return "No spending data"

    lines = []
    sorted_categories = sorted(by_category.items(), key=lambda x: x[1], reverse=True)
    max_len = max(len(cat) for cat, _ in sorted_categories)

    for category, amount in sorted_categories:
        lines.append(f"  {category:<{max_len}}  ${amount:>10,.2f}")

    return "\n".join(lines)


def _format_top_transactions(transactions: list, limit: int = 10) -> tuple[str, str]:
    """Format top transactions as HTML and plain text."""
    if not transactions:
        return "", ""

    # Sort by amount (most expensive first) and take top N
    sorted_txns = sorted(
        [t for t in transactions if t.get("amount", 0) < 0],
        key=lambda x: x.get("amount", 0)
    )[:limit]

    if not sorted_txns:
        return "", ""

    # HTML version
    html_items = []
    for txn in sorted_txns:
        html_items.append(f"""
            <div class="transaction">
                <div>
                    <div class="transaction-desc">{txn.get('description', 'Unknown')}</div>
                    <div class="transaction-date">{txn.get('date', '')} • {txn.get('category', 'Uncategorized')}</div>
                </div>
                <div class="amount spending">-${abs(txn.get('amount', 0)):,.2f}</div>
            </div>
        """)

    html = f"""
        <div class="transactions-section">
            <h2>Top {len(sorted_txns)} Transactions</h2>
            {''.join(html_items)}
        </div>
    """

    # Plain text version
    text_lines = [f"\nTOP {len(sorted_txns)} TRANSACTIONS", "-" * 25]
    for txn in sorted_txns:
        text_lines.append(
            f"  {txn.get('date', ''):<12} {txn.get('description', 'Unknown'):<30} ${abs(txn.get('amount', 0)):>10,.2f}"
        )
    text = "\n".join(text_lines)

    return html, text


def send_spending_summary(
    to_email: str,
    month: str,
    total_spent: float,
    by_category: dict,
    transactions: list | None = None,
    total_income: float = 0,
    threshold_crossed: float | None = None,
    smtp_email: str | None = None,
    smtp_password: str | None = None,
) -> bool:
    """
    Send a formatted spending summary email.

    Args:
        to_email: Recipient email address
        month: Month string (e.g., "1/2025")
        total_spent: Total spending amount (positive number)
        by_category: Dict of category -> amount spent
        transactions: Optional list of transaction dicts for top transactions
        total_income: Optional total income amount
        threshold_crossed: Optional threshold that was crossed (triggers alert)
        smtp_email: Sender email (defaults to SMTP_EMAIL env var)
        smtp_password: Email password (defaults to SMTP_PASSWORD env var)

    Returns:
        True if sent successfully
    """
    smtp_email = smtp_email or os.environ.get("SMTP_EMAIL")
    smtp_password = smtp_password or os.environ.get("SMTP_PASSWORD")

    if not smtp_email or not smtp_password:
        raise ValueError(
            "SMTP credentials not found. Set SMTP_EMAIL and SMTP_PASSWORD environment variables."
        )

    # Prepare template data
    title = f"Spending Summary - {month}"
    generated_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    # Income section
    income_html = ""
    income_text = ""
    if total_income > 0:
        income_html = f'<div style="margin-top: 15px;">Total Income</div><div class="total-income">+${total_income:,.2f}</div>'
        income_text = f"Total Income: +${total_income:,.2f}"

    # Alert section
    alert_html = ""
    alert_text = ""
    if threshold_crossed:
        alert_html = f"""
            <div class="alert-box">
                <strong>Threshold Alert!</strong><br>
                Your spending has crossed the ${threshold_crossed:,.0f} threshold.
            </div>
        """
        alert_text = f"⚠️ ALERT: Spending crossed ${threshold_crossed:,.0f} threshold!\n"

    # Format categories
    category_rows = _format_category_rows(by_category, total_spent)
    category_text = _format_category_text(by_category)

    # Format top transactions
    top_txn_html, top_txn_text = _format_top_transactions(transactions or [])

    # Build HTML email
    html_template = _get_spending_html_template()
    html_content = html_template.format(
        title=title,
        total_spent=total_spent,
        income_section=income_html,
        alert_section=alert_html,
        category_rows=category_rows,
        top_transactions_section=top_txn_html,
        generated_date=generated_date,
    )

    # Build plain text email
    text_content = f"""
{title}
{'=' * len(title)}

SUMMARY
-------
Total Spending: ${total_spent:,.2f}
{income_text}

{alert_text}
SPENDING BY CATEGORY
--------------------
{category_text}
{top_txn_text}

---
Generated on {generated_date}
Expense Tracker
"""

    # Create multipart message
    msg = MIMEMultipart("alternative")
    msg["From"] = smtp_email
    msg["To"] = to_email
    msg["Subject"] = f"💰 {title}" if threshold_crossed else title

    # Attach both versions (email clients will pick the best one)
    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
