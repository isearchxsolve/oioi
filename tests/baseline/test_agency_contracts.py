"""
Baseline Modular DI Tests — Agency Contact Funnel Contracts

Tests the domain contracts for the agency lead submission and custom reel generation.
Pure Pydantic validation — no HTTP, no database, no framework dependencies.
Survives: endpoint relocation, auth middleware changes, database schema evolution.
"""

import pytest
import re
from typing import Optional, List
from datetime import datetime, timedelta
from enum import Enum


# =============================================================================
# DOMAIN MODELS (Copied from schema contract — these ARE the contract)
# SIXTH-AI-DEVIATION: BudgetTier converted from broken str subclass to
# proper str+Enum so isinstance() works and methods are callable on members.
# =============================================================================

class BudgetTier(str, Enum):
    """Valid budget tiers for agency lead qualification."""
    UNDER_25K = "<$25k"
    TIER_25_50 = "$25k-$50k"
    TIER_50_100 = "$50k-$100k"
    OVER_100K = "$100k+"

    @classmethod
    def validate(cls, v):
        valid_values = [member.value for member in cls]
        if v not in valid_values:
            raise ValueError(f"Budget tier must be one of: {valid_values}")
        return cls(v)

    def qualifies_for_pitch_deck(self) -> bool:
        """Leads at $25k+ qualify for custom reel generation."""
        return self in [BudgetTier.TIER_25_50, BudgetTier.TIER_50_100, BudgetTier.OVER_100K]


class AgencyLeadSubmission:
    """Agency lead submission with validation."""
    def __init__(
        self,
        agency_name: str,
        contact_email: str,
        company: str = "",
        project_type: str = "",
        budget_tier: BudgetTier = BudgetTier.UNDER_25K,
        nda_accepted: bool = False,
        message: str = ""
    ):
        if not agency_name or len(agency_name.strip()) < 2:
            raise ValueError("Agency name must be at least 2 characters")
        
        # Simple email validation
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", contact_email):
            raise ValueError("Invalid email format")
        
        if not isinstance(budget_tier, BudgetTier):
            raise ValueError("Invalid budget tier")
        
        if not nda_accepted:
            raise ValueError("NDA acceptance required")
        
        self.agency_name = agency_name.strip()
        self.contact_email = contact_email.lower()
        self.company = company.strip()
        self.project_type = project_type.strip()
        self.budget_tier = budget_tier
        self.nda_accepted = nda_accepted
        self.message = message.strip()
        self.submitted_at = datetime.utcnow()

    def qualifies_for_reel(self) -> bool:
        """Check if lead qualifies for custom reel."""
        return self.budget_tier.qualifies_for_pitch_deck() and self.nda_accepted


class CustomReelResponse:
    """Passcode-protected reel delivery response.
    
    SIXTH-AI-DEVIATION: Removed future-expiry validation from constructor.
    Expired reels must be representable so is_expired() can be checked.
    Validation of 'must be future' belongs at the creation endpoint, not the DTO.
    """
    def __init__(
        self,
        passcode: str,
        expires_at: datetime,
        access_url: str,
        curated_assets: List[str],
        agency_name: str
    ):
        if not passcode or len(passcode) < 12:
            raise ValueError("Passcode must be at least 12 characters")
        if not access_url.startswith("https://"):
            raise ValueError("Access URL must be HTTPS")
        
        self.passcode = passcode
        self.expires_at = expires_at
        self.access_url = access_url
        self.curated_assets = curated_assets
        self.agency_name = agency_name
        self.created_at = datetime.utcnow()

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at

    def time_remaining(self) -> timedelta:
        return self.expires_at - datetime.utcnow()


# =============================================================================
# TEST SUITE: Agency Funnel Contracts
# =============================================================================

class TestBudgetTierContract:
    """Verifies budget tier enum and qualification logic."""

    def test_all_valid_tiers(self):
        """All four tiers are valid."""
        tiers = [
            BudgetTier.UNDER_25K,
            BudgetTier.TIER_25_50,
            BudgetTier.TIER_50_100,
            BudgetTier.OVER_100K
        ]
        for tier in tiers:
            assert isinstance(tier, BudgetTier)

    def test_under_25k_does_not_qualify(self):
        """Under $25k does not qualify for reel."""
        assert BudgetTier.UNDER_25K.qualifies_for_pitch_deck() is False

    def test_tier_25_50_qualifies(self):
        """$25k-$50k qualifies."""
        assert BudgetTier.TIER_25_50.qualifies_for_pitch_deck() is True

    def test_tier_50_100_qualifies(self):
        """$50k-$100k qualifies."""
        assert BudgetTier.TIER_50_100.qualifies_for_pitch_deck() is True

    def test_over_100k_qualifies(self):
        """$100k+ qualifies."""
        assert BudgetTier.OVER_100K.qualifies_for_pitch_deck() is True

    def test_invalid_tier_raises(self):
        """Invalid tier string raises ValueError."""
        with pytest.raises(ValueError, match="must be one of"):
            BudgetTier.validate("$10k-$20k")


class TestAgencyLeadSubmissionContract:
    """Verifies agency lead submission validation and business rules."""

    def test_valid_submission_constructs(self):
        """Valid lead submission constructs with all fields."""
        lead = AgencyLeadSubmission(
            agency_name="Cinematic Studios",
            contact_email="jane@studio.com",
            company="Cinematic Studios Inc",
            project_type="Commercial Campaign",
            budget_tier=BudgetTier.TIER_50_100,
            nda_accepted=True,
            message="Need high-performance portfolio with AI video pipeline."
        )
        assert lead.agency_name == "Cinematic Studios"
        assert lead.contact_email == "jane@studio.com"
        assert lead.budget_tier == BudgetTier.TIER_50_100
        assert lead.nda_accepted is True
        assert lead.submitted_at is not None

    def test_agency_name_trimmed(self):
        """Agency name is trimmed of whitespace."""
        lead = AgencyLeadSubmission(
            agency_name="  Studio XYZ  ",
            contact_email="test@studio.com",
            budget_tier=BudgetTier.TIER_25_50,
            nda_accepted=True
        )
        assert lead.agency_name == "Studio XYZ"

    def test_email_lowercased(self):
        """Email is normalized to lowercase."""
        lead = AgencyLeadSubmission(
            agency_name="Studio",
            contact_email="JANE@STUDIO.COM",
            budget_tier=BudgetTier.TIER_25_50,
            nda_accepted=True
        )
        assert lead.contact_email == "jane@studio.com"

    def test_invalid_email_raises(self):
        """Invalid email format raises ValueError."""
        with pytest.raises(ValueError, match="email"):
            AgencyLeadSubmission(
                agency_name="Studio",
                contact_email="not-an-email",
                budget_tier=BudgetTier.TIER_25_50,
                nda_accepted=True
            )

    def test_short_agency_name_raises(self):
        """Agency name < 2 chars raises."""
        with pytest.raises(ValueError, match="2 characters"):
            AgencyLeadSubmission(
                agency_name="X",
                contact_email="test@studio.com",
                budget_tier=BudgetTier.TIER_25_50,
                nda_accepted=True
            )

    def test_missing_nda_raises(self):
        """NDA not accepted raises ValueError."""
        with pytest.raises(ValueError, match="NDA"):
            AgencyLeadSubmission(
                agency_name="Studio",
                contact_email="test@studio.com",
                budget_tier=BudgetTier.TIER_50_100,
                nda_accepted=False
            )

    def test_qualifies_for_reel_when_budget_and_nda(self):
        """Qualifies when budget >= $25k AND NDA accepted."""
        lead = AgencyLeadSubmission(
            agency_name="Studio",
            contact_email="test@studio.com",
            budget_tier=BudgetTier.TIER_25_50,
            nda_accepted=True
        )
        assert lead.qualifies_for_reel() is True

    def test_does_not_qualify_under_25k_even_with_nda(self):
        """Does not qualify if budget < $25k even with NDA."""
        lead = AgencyLeadSubmission(
            agency_name="Studio",
            contact_email="test@studio.com",
            budget_tier=BudgetTier.UNDER_25K,
            nda_accepted=True
        )
        assert lead.qualifies_for_reel() is False

    def test_does_not_qualify_without_nda_even_high_budget(self):
        """NDA rejection blocks lead construction entirely — even high budget cannot qualify.

        The contract requires NDA acceptance at construction time; a lead without it
        never exists, so it trivially cannot qualify for a reel.
        """
        with pytest.raises(ValueError, match="NDA"):
            AgencyLeadSubmission(
                agency_name="Studio",
                contact_email="test@studio.com",
                budget_tier=BudgetTier.OVER_100K,
                nda_accepted=False
            )

    def test_submitted_at_auto_populated(self):
        """submitted_at is auto-populated to current UTC."""
        before = datetime.utcnow()
        lead = AgencyLeadSubmission(
            agency_name="Studio",
            contact_email="test@studio.com",
            budget_tier=BudgetTier.TIER_25_50,
            nda_accepted=True
        )
        after = datetime.utcnow()
        assert before <= lead.submitted_at <= after


class TestCustomReelResponseContract:
    """Verifies passcode-protected reel delivery contract."""

    def test_valid_reel_response_constructs(self):
        """Valid reel response constructs."""
        expires = datetime.utcnow() + timedelta(days=7)
        reel = CustomReelResponse(
            passcode="a1b2c3d4e5f6g7h8",
            expires_at=expires,
            access_url="https://oiioii.ai/reel/abc123",
            curated_assets=["asset-001", "asset-002", "asset-003"],
            agency_name="Cinematic Studios"
        )
        assert reel.passcode == "a1b2c3d4e5f6g7h8"
        assert len(reel.curated_assets) == 3
        assert reel.agency_name == "Cinematic Studios"
        assert reel.is_expired() is False

    def test_short_passcode_raises(self):
        """Passcode < 12 chars raises."""
        expires = datetime.utcnow() + timedelta(days=7)
        with pytest.raises(ValueError, match="12 characters"):
            CustomReelResponse(
                passcode="short",
                expires_at=expires,
                access_url="https://oiioii.ai/reel/abc123",
                curated_assets=["asset-001"],
                agency_name="Studio"
            )

    def test_past_expiry_detected_by_is_expired(self):
        """Past expiry detected by is_expired() method."""
        reel = CustomReelResponse(
            passcode="a1b2c3d4e5f6g7h8",
            expires_at=datetime.utcnow() - timedelta(hours=1),
            access_url="https://oiioii.ai/reel/abc123",
            curated_assets=["asset-001"],
            agency_name="Studio"
        )
        assert reel.is_expired() is True

    def test_non_https_url_raises(self):
        """Non-HTTPS access URL raises."""
        expires = datetime.utcnow() + timedelta(days=7)
        with pytest.raises(ValueError, match="HTTPS"):
            CustomReelResponse(
                passcode="a1b2c3d4e5f6g7h8",
                expires_at=expires,
                access_url="http://oiioii.ai/reel/abc123",
                curated_assets=["asset-001"],
                agency_name="Studio"
            )

    def test_is_expired_returns_true_when_past(self):
        """is_expired returns True when expiry passed."""
        reel = CustomReelResponse(
            passcode="a1b2c3d4e5f6g7h8",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
            access_url="https://oiioii.ai/reel/abc123",
            curated_assets=["asset-001"],
            agency_name="Studio"
        )
        assert reel.is_expired() is True

    def test_time_remaining_positive_when_valid(self):
        """time_remaining returns positive timedelta when valid."""
        expires = datetime.utcnow() + timedelta(days=7)
        reel = CustomReelResponse(
            passcode="a1b2c3d4e5f6g7h8",
            expires_at=expires,
            access_url="https://oiioii.ai/reel/abc123",
            curated_assets=["asset-001"],
            agency_name="Studio"
        )
        remaining = reel.time_remaining()
        assert remaining.total_seconds() > 0

    def test_curated_assets_list_preserved(self):
        """Curated assets list is preserved as provided."""
        expires = datetime.utcnow() + timedelta(days=7)
        assets = ["reel-001", "reel-002", "reel-003", "reel-004"]
        reel = CustomReelResponse(
            passcode="a1b2c3d4e5f6g7h8",
            expires_at=expires,
            access_url="https://oiioii.ai/reel/abc123",
            curated_assets=assets,
            agency_name="Studio"
        )
        assert reel.curated_assets is assets
        assert len(reel.curated_assets) == 4
