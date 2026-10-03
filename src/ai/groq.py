"""One multimodal model on Groq does both AI jobs: read a receipt image (OCR) and check it against what the employee claimed."""
import base64
import json

import httpx
from pydantic import ValidationError

from config.setting import settings
from src.errors import AppError
from src.resources import Resources
from src.pydantic_models.receipt import ClaimCheck, ReceiptData


class Groq:
    def read_receipt(self, image: bytes, mime: str) -> ReceiptData:
        """OCR: the model sees only the image (not the claim, so the claim cannot bias what it reads) and returns the receipt as JSON."""
        prompt = (
            "Read this bill or receipt. Answer with JSON only, matching this schema:\n"
            f"{json.dumps(ReceiptData.model_json_schema())}\n"
            "amount is the grand total including taxes, as a number. paid_by is 'Company' only if a corporate or company card paid, "
            "otherwise 'Employee'. description is one short line on what was bought. bill_date is YYYY-MM-DD."
        )
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image).decode()}"}},
        ]
        return self._parse(ReceiptData, self._ask(content), "a readable bill")

    def check_claim(self, head: str, receipt: ReceiptData) -> ClaimCheck:
        """Give the model the claimed head and what was read from the bill, and ask whether they fit. Text only, so it is quick."""
        prompt = (
            f"An employee claims the bill below as '{head}', which means {settings.head_meanings[head]}.\n"
            f"What was read from the bill:\n{receipt.model_dump_json()}\n"
            "Does the bill fit that claim? Judge only the kind of business that issued the bill and its main purpose. "
            "Extra items on the bill (for example laundry or a mini bar on a hotel bill) do NOT make it a mismatch. "
            "Answer with JSON only: "
            '{"merchant_type": a short label for the kind of business, e.g. restaurant, taxi, hotel, petrol pump, '
            '"matches": true or false, "issue": null if it fits, otherwise one short sentence saying what the bill is and why it does not fit}'
        )
        return self._parse(ClaimCheck, self._ask([{"type": "text", "text": prompt}]), "a verdict")

    def _ask(self, content: list) -> str:
        """Send one message to the model and return its reply text. The model is told to answer in JSON."""
        if not settings.groq_api_key:
            raise AppError(503, "GROQ_API_KEY is not set, so receipts cannot be checked")
        body = {
            "model": settings.groq_model, "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_object"}, "temperature": 0,
        }
        try:
            reply = Resources.get().http.post(settings.groq_url, json=body, headers={"Authorization": f"Bearer {settings.groq_api_key}"})  # the shared client
            reply.raise_for_status()
            return reply.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError) as error:
            raise AppError(502, f"The AI service failed: {error}")

    def _parse(self, model, text: str, what: str):
        """Turn the model's reply into a validated Pydantic object; a reply that does not fit is an error, never a guess."""
        try:
            return model.model_validate_json(text)
        except ValidationError:
            raise AppError(502, f"The AI service did not return {what}")
