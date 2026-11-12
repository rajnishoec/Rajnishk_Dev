"""Tiny invoice calculator with intentionally uncovered business branches."""

from decimal import Decimal


def invoice_total(subtotal: str, customer: str = "standard", shipping: str = "standard") -> Decimal:
    amount = Decimal(subtotal)
    if amount < 0:
        raise ValueError("Subtotal cannot be negative.")
    if customer == "vip":
        amount *= Decimal("0.8")
    elif customer == "student":
        amount *= Decimal("0.9")
    elif customer != "standard":
        raise ValueError("Unknown customer type.")
    if shipping == "express":
        amount += Decimal("15")
    elif shipping != "standard":
        raise ValueError("Unknown shipping method.")
    if amount < 50 and shipping == "standard":
        amount += Decimal("5")
    return amount.quantize(Decimal("0.01"))


def refund_amount(paid: str, days: int) -> Decimal:
    if days < 0:
        raise ValueError("Days cannot be negative.")
    if days <= 30:
        return Decimal(paid)
    if days <= 60:
        return (Decimal(paid) / 2).quantize(Decimal("0.01"))
    return Decimal("0.00")
