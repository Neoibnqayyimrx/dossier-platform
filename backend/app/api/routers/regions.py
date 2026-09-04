"""Region profiles, served to the frontend (P15a).

WHY this endpoint: Module 1 is the one part of a CTD that genuinely
varies by region -- which certificates and declarations a filing must
carry is a NAFDAC fact, not a universal one. The wizard has to ask for
exactly those, and the alternative is a hard-coded list in TypeScript
that drifts from the rules the moment a requirement changes.

Same reasoning as /enums and /sections: derive, never duplicate. The
values here are the very ones R13 and R16 validate against, so a UI built
from this endpoint cannot ask for a different set than the rule engine
enforces.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.ctd.region_profiles import REGION_PROFILES
from app.models.enums import Region

router = APIRouter(prefix="/regions", tags=["regions"])


class Module1SlotRead(BaseModel):
    slot_id: str
    title: str


class RegionProfileRead(BaseModel):
    region: Region
    # Empty for a region whose Module 1 requirements have not been
    # confirmed against current agency guidance (EU today) -- an empty
    # list means "not modelled", not "nothing is required". See
    # EU_PROFILE's comment in app/ctd/region_profiles.py.
    required_certificate_types: list[str]
    required_declaration_types: list[str]
    module1_slots: list[Module1SlotRead]


@router.get("", response_model=list[RegionProfileRead])
async def list_region_profiles() -> list[RegionProfileRead]:
    return [
        RegionProfileRead(
            region=profile.region,
            required_certificate_types=[t.value for t in profile.required_certificate_types],
            required_declaration_types=[t.value for t in profile.required_declaration_types],
            module1_slots=[
                Module1SlotRead(slot_id=slot.slot_id, title=slot.title)
                for slot in profile.module1_slots
            ],
        )
        for profile in REGION_PROFILES.values()
    ]
