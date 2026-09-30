"""Gemini reads a receipt image into structured data."""
import base64
import json

import httpx
from pydantic import ValidationError

from config.setting import settings
from src.errors import AppError
from src.pydantic_models.receipt import ReceiptData


class Gemini:
    def read_receipt(self, image: bytes, mime: str) -> ReceiptData:
        """Send the image to Gemini, ask for JSON in the ReceiptData shape, and validate the answer."""
        if not settings.gemini_api_key:
            raise AppError(503, "GEMINI_API_KEY is not set, so receipts cannot be read")
        prompt = (
            "Read this bill or receipt and answer with JSON only, matching this schema:\n"
            f"{json.dumps(ReceiptData.model_json_schema())}\n"
            "amount is the grand total including taxes. paid_by is 'Company' only if a corporate or company card paid, otherwise 'Employee'. "
            "description is one short line on what was bought. Dates as YYYY-MM-DD."
        )
        body = {
            "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime, "data": base64.b64encode(image).decode()}}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
        try:
            reply = httpx.post(url, json=body, headers={"x-goog-api-key": settings.gemini_api_key}, timeout=60)
            reply.raise_for_status()
            return ReceiptData.model_validate_json(reply.json()["candidates"][0]["content"]["parts"][0]["text"])
        except (httpx.HTTPError, KeyError, IndexError) as error:
            raise AppError(502, f"Gemini could not read the receipt: {error}")
        except ValidationError:
            raise AppError(502, "Gemini's answer was not a usable receipt (is this image a bill?)")
