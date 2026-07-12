"""Controlled vocabularies shared across the data model.

WHY centralize enums here: a regulator's dossier must be internally
consistent, and a Python `enum.Enum` backed by a Postgres `ENUM` type means
the database physically cannot store a value that isn't on the approved
list (e.g. "Tablets" for a capsule product, or a made-up GMP status). That
turns a whole class of copy-paste bug into something the schema itself
rejects, rather than something a rule has to catch after the fact.

Every enum here is deliberately a short, real-world list. Extend it by
adding a member — never by writing a bare string into a model field.
"""

from __future__ import annotations

import enum


class Region(str, enum.Enum):
    """Which regulatory authority a Project targets. Drives which Module 1
    variant and which CTD/eCTD builder run later (P08/P09) — but the models
    themselves never branch on this value; see AGENTS.md design notes."""

    NAFDAC = "NAFDAC"
    FDA = "FDA"
    EU = "EU"


class RegistrationType(str, enum.Enum):
    NEW = "new"
    RENEWAL = "renewal"
    VARIATION = "variation"


class DosageForm(str, enum.Enum):
    """A controlled, extensible list. Add members as new dosage forms are
    onboarded — never store a dosage form as free text."""

    TABLET = "tablet"
    CAPSULE_HARD = "hard gelatin capsule"
    CAPSULE_SOFT = "soft gelatin capsule"
    SYRUP = "syrup"
    SUSPENSION = "suspension"
    INJECTION = "injection"
    CREAM = "cream"
    OINTMENT = "ointment"


class LegalStatus(str, enum.Enum):
    """How the product may be dispensed."""

    PRESCRIPTION_ONLY = "prescription-only"
    PHARMACY_ONLY = "pharmacy-only"
    OVER_THE_COUNTER = "over-the-counter"
    CONTROLLED_SUBSTANCE = "controlled-substance"


class CompendialStatus(str, enum.Enum):
    """Which pharmacopoeia a material's spec is claimed against. NOTE: this
    stores only the CITATION (e.g. "BP") — never the monograph text itself.
    See AGENTS.md §5: pharmacopoeia monographs are copyrighted and must not
    be ingested into the knowledge base."""

    BP = "BP"
    USP_NF = "USP-NF"
    PH_EUR = "Ph. Eur."
    JP = "JP"
    IN_HOUSE = "in-house"


class ExcipientFunction(str, enum.Enum):
    DILUENT = "diluent"
    BINDER = "binder"
    DISINTEGRANT = "disintegrant"
    LUBRICANT = "lubricant"
    GLIDANT = "glidant"
    COATING_AGENT = "coating agent"
    PRESERVATIVE = "preservative"
    SWEETENER = "sweetener"
    COLORANT = "colorant"
    CAPSULE_SHELL = "capsule shell"


class ManufacturerRole(str, enum.Enum):
    """A Product can list several manufacturers playing different roles —
    e.g. the finished-product site is often not the same site that makes
    the API. `ActiveIngredient.manufacturer` points at one of these rows."""

    FINISHED_PRODUCT = "finished product"
    API_MANUFACTURER = "API manufacturer"
    PACKAGING_SITE = "packaging site"
    CONTRACT_MANUFACTURER = "contract manufacturer"


class GMPStatus(str, enum.Enum):
    CERTIFIED = "certified"
    PENDING = "pending"
    EXPIRED = "expired"
    NOT_CERTIFIED = "not certified"


class PackagingComponent(str, enum.Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    ARTWORK = "artwork"
    LABEL = "label"
    LEAFLET = "leaflet"
    CARTON = "carton"


class StabilityStudyType(str, enum.Enum):
    ACCELERATED = "accelerated"
    LONG_TERM = "long-term"
    INTERMEDIATE = "intermediate"


class ClinicalKind(str, enum.Enum):
    BIOEQUIVALENCE = "bioequivalence"
    LITERATURE = "literature"
    CLINICAL_STUDY = "clinical study"
