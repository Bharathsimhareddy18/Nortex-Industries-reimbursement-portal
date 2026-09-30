"""Every price-based rule from the Nortex travel policy (NTX-HR-POL-11), in one place.

Change a number here (or override it with an environment variable / .env entry) and the whole app follows.
"""
from decimal import Decimal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


RM, HOD, HOD_DIV, MD = "Reporting Manager", "Head of Department", "Head of Division", "MD"


class ApprovalBand(BaseModel):
    """One row of the policy's approval table: amounts up to `up_to` (inclusive) need ALL of these approvers."""

    up_to: Decimal | None  # None means no upper limit
    approvers: list[str]


class Settings(BaseSettings):
    # Reads .env if present; an env var such as ADVANCE_MAX_PCT=50 overrides the default below.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Policy section 2: the approval table, row for row. The first band whose `up_to` covers the amount applies.
    # Every band lists the full set of approvers, in the order they approve.
    approval_bands: list[ApprovalBand] = [
        ApprovalBand(up_to=Decimal("25000"), approvers=[RM]),  # up to 25,000
        ApprovalBand(up_to=Decimal("75000"), approvers=[RM, HOD]),  # 25,001 - 75,000
        ApprovalBand(up_to=Decimal("200000"), approvers=[RM, HOD, HOD_DIV]),  # 75,001 - 2,00,000
        ApprovalBand(up_to=None, approvers=[RM, HOD, HOD_DIV, MD]),  # above 2,00,000
    ]
    # Any international trip needs everyone, whatever the amount.
    international_approvers: list[str] = [RM, HOD, HOD_DIV, MD]

    # Policy 3.1: lodging limit per night (room tariff, excluding tax), by city tier.
    lodging_tier1: Decimal = Decimal("6000")
    lodging_tier2: Decimal = Decimal("4000")
    lodging_tier3: Decimal = Decimal("2800")

    # Policy 3.3: meal limit per full day, by city tier. Tier 2 and below share one limit.
    meals_tier1: Decimal = Decimal("1500")
    meals_tier2_and_below: Decimal = Decimal("1000")
    meal_bill_required_above: Decimal = Decimal("500")  # meal claims above this need a bill

    # Policy 3.5: hosted meals above this need prior Head of Department approval.
    entertainment_approval_above: Decimal = Decimal("2000")

    # Policy 1.2: advance may be at most this % of the estimated employee-borne cost.
    advance_max_pct: Decimal = Decimal("60")

    # Policy 5.1: settlement must be filed within this many calendar days of return.
    settlement_days: int = 7

    # Policy 5.4: Finance pays on these days of the month.
    payment_run_days: list[int] = [10, 25]

    # Policy 3.1: which cities are Tier 1 (lower-case). Tier 2 is empty until Nortex lists its Tier 2 cities; the rest are Tier 3.
    tier1_cities: list[str] = [
        "bengaluru", "bangalore", "mumbai", "delhi", "new delhi", "gurugram", "gurgaon", "noida",
        "ghaziabad", "faridabad", "hyderabad", "chennai", "pune", "kolkata",
    ]
    tier2_cities: list[str] = []

    # Who performs each Finance step (employee codes). Ravi Menon, Manager - Finance Shared Services, releases advances and
    # verifies claims; Kavitha Balan, Controller, releases the final payout. Verifier and releaser are deliberately different people.
    finance_advance_code: str = "NX-3305"
    finance_verify_code: str = "NX-3305"
    finance_payout_code: str = "NX-3300"

    # Demo login: every employee uses this one password (dummy auth). Override with the DEMO_PASSWORD env var.
    demo_password: str = "nortex123"
    session_hours: int = 12  # how long a login stays valid


settings = Settings()
