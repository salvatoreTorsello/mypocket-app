from anthropic import AsyncAnthropic

from app.config import settings
from app.integrations.anthropic.parser import (
    ExpenseParsed,
    ReceiptExtracted,
    parse_expense_json,
    parse_receipt_json,
)
from app.integrations.anthropic.prompts import PARSE_EXPENSE_SYSTEM, RECEIPT_EXTRACT_SYSTEM

_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def parse_expense(text: str) -> ExpenseParsed:
    msg = await get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=PARSE_EXPENSE_SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    return parse_expense_json(msg.content[0].text)


async def extract_receipt(image_b64: str, mime_type: str = "image/jpeg") -> ReceiptExtracted:
    msg = await get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=RECEIPT_EXTRACT_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": image_b64,
                    },
                },
                {"type": "text", "text": "Extract the receipt data."},
            ],
        }],
    )
    return parse_receipt_json(msg.content[0].text)
