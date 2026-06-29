import json
import re
from dataclasses import dataclass, field


@dataclass
class ExpenseParsed:
    amount: float
    merchant: str | None
    date: str | None          # "YYYY-MM-DD" or None (= today)
    category_suggestion: str
    category_confidence: float
    likely_shared: bool
    vouchers_detected: bool
    clarification_needed: str | None

    @property
    def needs_clarification(self) -> bool:
        return bool(self.clarification_needed) or self.category_confidence < 0.70

    @property
    def is_valid(self) -> bool:
        return self.amount > 0


@dataclass
class ReceiptExtracted:
    merchant: str
    date: str | None
    total: float
    items: list[dict] = field(default_factory=list)
    payment_method: str = "unknown"
    category_suggestion: str = "Other"
    category_confidence: float = 0.5
    confidence: float = 0.0

    @property
    def is_readable(self) -> bool:
        return self.confidence >= 0.4


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"No JSON found in Claude response: {text[:300]}")


def parse_expense_json(text: str) -> ExpenseParsed:
    d = _extract_json(text)
    return ExpenseParsed(
        amount=float(d.get("amount") or 0),
        merchant=d.get("merchant") or None,
        date=d.get("date") or None,
        category_suggestion=d.get("category_suggestion") or "Other",
        category_confidence=float(d.get("category_confidence") or 0.5),
        likely_shared=bool(d.get("likely_shared", False)),
        vouchers_detected=bool(d.get("vouchers_detected", False)),
        clarification_needed=d.get("clarification_needed") or None,
    )


def parse_receipt_json(text: str) -> ReceiptExtracted:
    d = _extract_json(text)
    return ReceiptExtracted(
        merchant=d.get("merchant") or "Unknown",
        date=d.get("date") or None,
        total=float(d.get("total") or 0),
        items=(d.get("items") or [])[:5],
        payment_method=d.get("payment_method") or "unknown",
        category_suggestion=d.get("category_suggestion") or "Other",
        category_confidence=float(d.get("category_confidence") or 0.5),
        confidence=float(d.get("confidence") or 0),
    )
