"""Re-target a seeded project as an FDA original application (gap Phase 4c).

The platform's fixtures are NAFDAC filings, because that is where the
source dossier came from. Modules 2-5 are common to every ICH region, so the
same product is a fair test of FDA publishing -- the parts that differ are
Module 1 and the admin block, and those are exactly what this changes.

WHY the identifiers are what they are, since a seed must never look like a
real filing:

- D-U-N-S `999999999` is the value FDA's own technical conformance guide
  (3.1.1) tells an applicant to enter when a D-U-N-S number cannot be
  obtained before submission. It is FDA-sanctioned AND unmistakably not a
  company's number, which is the combination a fixture needs.
- Application number `000000` has the six-digit shape FDA's backbone
  requires (so R34 is satisfied and the builder runs) and is chosen so it
  cannot be mistaken for, or collide with, an application FDA has issued.
"""

from __future__ import annotations

from app.models import FDAApplicationType, Project, Region, RegistrationType

SEED_DUNS_NUMBER = "999999999"
SEED_APPLICATION_NUMBER = "000000"


def as_fda_original_application(
    project: Project, application_type: FDAApplicationType = FDAApplicationType.ANDA
) -> Project:
    """`project`, changed in place into an FDA original application.

    ANDA by default: every seeded product is a multisource generic, and an
    ANDA is the US application for exactly that. `registration_type` becomes
    NEW because FDA has no renewal (rule R35) -- a NAFDAC renewal is, in the
    US, a first application.
    """
    project.region = Region.FDA
    project.product.registration_type = RegistrationType.NEW
    project.application_number = SEED_APPLICATION_NUMBER
    project.fda_application_type = application_type
    if project.applicant is not None:
        project.applicant.duns_number = SEED_DUNS_NUMBER
    return project
