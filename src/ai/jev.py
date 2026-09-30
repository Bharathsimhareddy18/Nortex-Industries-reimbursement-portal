"""Jev says what kind of business issued a bill."""
import httpx

from config.setting import settings
from src.errors import AppError

# The answers Jev may give, each with a description it uses to decide.
MERCHANT_TYPES = {
    "restaurant": "Restaurants, cafes and food outlets",
    "cab": "Taxi and ride-hailing trips",
    "hotel": "Hotels and lodging",
    "airline": "Flights and airline tickets",
    "fuel": "Petrol pumps and fuel",
    "pharmacy": "Pharmacies and medical stores",
    "coworking": "Co-working spaces and office services",
    "retail": "Shops and general retail",
    "other": "Anything else",
}


class Jev:
    def classify(self, text: str) -> tuple[str, float]:
        """One Choice question about the receipt text. Returns (merchant type, confidence from 0 to 1)."""
        if not settings.jev_api_key:
            raise AppError(503, "JEV_API_KEY is not set, so receipts cannot be checked")
        body = {
            "state": text[:4000],
            "model": settings.jev_model,
            "questions": {"merchant": {"type": "choice", "instructions": "What kind of business issued this bill?", "criteria": MERCHANT_TYPES}},
        }
        try:
            reply = httpx.post(settings.jev_url, json=body, headers={"Authorization": f"Bearer {settings.jev_api_key}"}, timeout=15)
            reply.raise_for_status()
            answer = reply.json()["answers"]["merchant"]
            return answer["choice"], float(answer["confidence"])
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise AppError(502, f"Jev could not check the receipt: {error}")
