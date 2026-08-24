from enum import Enum
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

class BudgetTierEnum(str, Enum):
    COMMERCIAL_MICRO = "COMMERCIAL_MICRO"
    COMMERCIAL_TIER1 = "COMMERCIAL_TIER1"
    FEATURE = "FEATURE"
    INDIE = "INDIE"

class AgencyInquiryCreate(BaseModel):
    client_name: str = Field(..., min_length=2, max_length=100)
    client_email: EmailStr
    agency_or_company: str = Field(..., min_length=2, max_length=100)
    project_budget_tier: BudgetTierEnum
    project_brief: str = Field(..., min_length=10, max_length=5000)

class AgencyInquiryResponse(BaseModel):
    status: str
    inquiry_id: str
    message: str

@router.post("/inquire", response_model=AgencyInquiryResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def submit_agency_inquiry(request: Request, payload: AgencyInquiryCreate):
    return AgencyInquiryResponse(
        status="success",
        inquiry_id="inq_" + payload.client_name.lower().replace(" ", "_")[:10],
        message="Inquiry logged. Pitch kit dispatched.",
    )
