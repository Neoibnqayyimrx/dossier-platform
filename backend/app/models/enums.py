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
    onboarded — never store a dosage form as free text.

    Grouped by route/category (oral solid, oral liquid, parenteral,
    topical, ophthalmic/otic/nasal, rectal/vaginal, inhalation) because
    that's how a CTD reviewer actually thinks about a dossier's Module 3.2.P
    content -- modified-release/enteric-coated variants get their own
    members, not a shared generic "tablet", because their dissolution
    specs and stability considerations genuinely differ."""

    # -- oral solid --
    TABLET = "tablet"
    TABLET_CHEWABLE = "chewable tablet"
    TABLET_DISPERSIBLE = "dispersible tablet"
    TABLET_EFFERVESCENT = "effervescent tablet"
    TABLET_ORODISPERSIBLE = "orodispersible tablet"
    TABLET_ENTERIC_COATED = "enteric-coated tablet"
    TABLET_EXTENDED_RELEASE = "extended-release tablet"
    CAPSULE_HARD = "hard gelatin capsule"
    CAPSULE_SOFT = "soft gelatin capsule"
    GRANULES = "granules"
    POWDER_FOR_ORAL_SUSPENSION = "powder for oral suspension"
    LOZENGE = "lozenge"

    # -- oral liquid --
    SYRUP = "syrup"
    SUSPENSION = "suspension"
    SOLUTION_ORAL = "oral solution"
    ELIXIR = "elixir"
    EMULSION_ORAL = "oral emulsion"

    # -- parenteral --
    INJECTION = "injection"  # generic bucket; prefer a specific member below when known
    INJECTION_SOLUTION = "solution for injection"
    POWDER_FOR_INJECTION = "powder for injection"
    INFUSION = "solution for infusion"

    # -- topical --
    CREAM = "cream"
    OINTMENT = "ointment"
    GEL = "gel"
    LOTION = "lotion"
    PASTE = "paste"
    TRANSDERMAL_PATCH = "transdermal patch"

    # -- ophthalmic / otic / nasal --
    EYE_DROPS = "eye drops"
    EYE_OINTMENT = "eye ointment"
    EAR_DROPS = "ear drops"
    NASAL_SPRAY = "nasal spray"

    # -- rectal / vaginal --
    SUPPOSITORY = "suppository"
    PESSARY = "pessary"
    ENEMA = "enema"

    # -- inhalation --
    INHALER_MDI = "metered-dose inhaler"
    INHALER_DPI = "dry powder inhaler"
    NEBULISER_SOLUTION = "nebuliser solution"


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


class KBSource(str, enum.Enum):
    """Allowlisted origins for knowledge-base documents (P03). Deliberately
    excludes pharmacopoeia bodies (USP, Ph. Eur., BP, JP) — AGENTS.md §5
    forbids ingesting their monograph text, and a source the DB can't store
    is a source the ingest pipeline physically cannot accept."""

    ICH = "ICH"
    FDA = "FDA"
    EMA = "EMA"
    WHO = "WHO"
    NAFDAC = "NAFDAC"


class CertificateType(str, enum.Enum):
    """A regulatory certificate a real human must obtain from a third party
    (a regulator, a lab, EDQM) and attach to the dossier -- never something
    the platform can generate content for. See app.templating.placeholders
    for how a not-yet-attached certificate becomes a clearly-marked
    placeholder document at assembly time instead of a silent gap."""

    CPP = "CPP"  # Certificate of Pharmaceutical Product (WHO format)
    GMP = "GMP"  # Good Manufacturing Practice certificate, site-specific
    CEP = "CEP"  # Certificate of Suitability to a Ph. Eur. monograph (EDQM)
    COA = "CoA"  # Certificate of Analysis, batch-specific
    FREE_SALE = "free-sale-certificate"


class NarrativeStatus(str, enum.Enum):
    """Human review state of one LLM-generated narrative slot (P05).
    AGENTS.md §5: unreviewed narrative must never reach a rendered
    package, so the template context builder only reads PENDING vs
    reviewed off this value — never off the mere existence of an
    output string."""

    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"


class KBLicense(str, enum.Enum):
    """Redistribution basis a kb_document must be tagged with to be ingested.
    ICH harmonised guidelines are adopted verbatim into national regulation
    by design, so they're freely redistributable; agency guidance documents
    are published by governments for exactly this kind of reuse. Anything
    that doesn't fit one of these categories (e.g. a copyrighted
    pharmacopoeia monograph) has no member here and is rejected at ingest —
    see services/knowledge/ingest.py."""

    ICH_HARMONISED = "ich-harmonised-guideline"
    GOVERNMENT_PUBLIC = "government-public-guidance"
    PUBLIC_DOMAIN = "public-domain"
