"""Travel filing document helpers: text formatters now, payload builders in a later increment."""
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")

_ONES = ("", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven",
         "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen")
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")
_SCALES = ((10 ** 9, "Billion"), (10 ** 6, "Million"), (1000, "Thousand"))


def _d(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def date_range(start, end) -> str:
    """Zero-padded range as the official forms print it: 'September 01-04, 2026'."""
    s, e = _d(start), _d(end)
    if e < s:
        s, e = e, s
    if s == e:
        return f"{MONTHS[s.month - 1]} {s.day:02d}, {s.year}"
    if (s.year, s.month) == (e.year, e.month):
        return f"{MONTHS[s.month - 1]} {s.day:02d}-{e.day:02d}, {s.year}"
    if s.year == e.year:
        return f"{MONTHS[s.month - 1]} {s.day:02d} - {MONTHS[e.month - 1]} {e.day:02d}, {s.year}"
    return (f"{MONTHS[s.month - 1]} {s.day:02d}, {s.year} - "
            f"{MONTHS[e.month - 1]} {e.day:02d}, {e.year}")


def _below_thousand(n: int) -> str:
    words = []
    if n >= 100:
        words.append(_ONES[n // 100] + " Hundred")
        n %= 100
    if n >= 20:
        words.append(_TENS[n // 10])
        n %= 10
    if n:
        words.append(_ONES[n])
    return " ".join(w for w in words if w)


def _int_words(n: int) -> str:
    if n == 0:
        return "Zero"
    parts = []
    for size, name in _SCALES:
        if n >= size:
            parts.append(_below_thousand(n // size) + " " + name)
            n %= size
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def peso_words(amount) -> str:
    """'Four Hundred Fifty Pesos', 'Five Hundred Fifty Pesos and 50/100'."""
    amt = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amt < 0:
        raise ValueError("An amount in words cannot be negative.")
    pesos, centavos = int(amt), int((amt - int(amt)) * 100)
    out = f"{_int_words(pesos)} {'Peso' if pesos == 1 else 'Pesos'}"
    return f"{out} and {centavos:02d}/100" if centavos else out


def money(amount) -> str:
    """'1,060' for a whole amount, '1,060.50' otherwise."""
    amt = Decimal(str(amount or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amt:,.0f}" if amt == amt.to_integral_value() else f"{amt:,.2f}"
