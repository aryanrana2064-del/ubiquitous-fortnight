"""Receipt / account slip as simple HTML that Qt's text engine prints on ANY Windows printer. No Qt here (unit-testable).

A receipt shows the shop, the customer, one or more ledger entries, the totals of those entries and the customer's
balance right now. One narrow column, so it prints well on A5 or A4 as well as on custom paper sizes.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Optional, Sequence

from . import dates, money
from .labels import JAMA_LABEL, UDHAAR_LABEL, type_label
from .service import Customer, Transaction



def receipt_title(entries: Sequence[Transaction]) -> str:
    if len(entries) > 1:
        return "ACCOUNT SLIP"
    return "PAYMENT RECEIPT" if entries and entries[0].txn_type == "JAMA" else "RECEIPT"


def _balance_line(balance_paise: int) -> tuple[str, str]:
    if balance_paise > 0:
        return "Balance due", money.format_inr(balance_paise)
    if balance_paise < 0:
        return "Advance", money.format_inr(-balance_paise)
    return "Balance", money.format_inr(0) + " (settled)"


def receipt_html(customer: Customer, entries: Sequence[Transaction], balance_paise: int, shop_name: str = "",
                 shop_details: str = "", printed_at: Optional[datetime] = None, font_pt: float = 11.0) -> str:
    """HTML of a receipt for ``entries`` of ``customer``; ``balance_paise`` is the balance right now."""
    e = escape
    now = printed_at or datetime.now()
    total_u = sum(t.amount_paise for t in entries if t.txn_type == "UDHAAR")
    total_j = sum(t.amount_paise for t in entries if t.txn_type == "JAMA")

    def pair(left: str, right: str, bold: bool = False) -> str:
        l, r = (f"<b>{e(left)}</b>", f"<b>{e(right)}</b>") if bold else (e(left), e(right))
        return f"<tr><td>{l}</td><td align='right'>{r}</td></tr>"

    parts = [f"<body style='font-family:Arial; font-size:{font_pt:g}pt;'>"]
    parts.append(f"<div align='center'><b style='font-size:{font_pt + 3:g}pt;'>{e(shop_name or 'VX7 KHATA PRO')}</b></div>")
    if shop_details:
        parts.append(f"<div align='center'>{e(shop_details).replace(chr(10), '<br/>')}</div>")
    parts.append("<hr/>")
    parts.append(f"<div align='center'><b>{receipt_title(entries)}</b></div>")
    parts.append("<table width='100%' cellspacing='0' cellpadding='1'>")
    parts.append(pair("Date", now.strftime("%d-%m-%Y %H:%M")))
    parts.append("</table>")
    parts.append(f"<div><b>{e(customer.name)}</b></div>")
    if customer.mobile:
        parts.append(f"<div>{e(customer.mobile)}</div>")
    parts.append("<hr/>")

    for t in entries:
        parts.append(f"<div><b>{e(t.item)}</b></div>")
        parts.append(f"<div>{dates.format_date(t.txn_date)} &nbsp;{e(type_label(t.txn_type))}</div>")
        qty_rate = ""
        if t.quantity and t.rate_paise:
            qty_rate = f"{t.quantity} x {money.format_inr(t.rate_paise, symbol=False)}"
        elif t.quantity:
            qty_rate = f"Qty {t.quantity}"
        parts.append("<table width='100%' cellspacing='0' cellpadding='1'>"
                     + pair(qty_rate, money.format_inr(t.amount_paise), bold=True) + "</table>")
        if t.notes:
            parts.append(f"<div><i>{e(' '.join(t.notes.split()))}</i></div>")
        parts.append("<hr/>")

    parts.append("<table width='100%' cellspacing='0' cellpadding='1'>")
    if total_u:
        parts.append(pair(f"Total {UDHAAR_LABEL}", money.format_inr(total_u)))
    if total_j:
        parts.append(pair(f"Total {JAMA_LABEL}", money.format_inr(total_j)))
    label, value = _balance_line(balance_paise)
    parts.append(pair(label, value, bold=True))
    parts.append("</table>")
    parts.append("<hr/>")
    parts.append("<div align='center'>Thank you!</div>")
    parts.append("</body>")
    return "".join(parts)
