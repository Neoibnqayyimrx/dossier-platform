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


class SubmissionType(str, enum.Enum):
    """What KIND of application this filing is — which decides how much of
    the CTD it owes (P17).

    WHY this exists as a controlled vocabulary rather than being inferred:
    a multisource (generic) dossier does not repeat the originator's animal
    studies, so Module 4 and Modules 2.4-2.7 are *declared* not applicable
    and owe a statement citing the guideline. A new chemical entity owes
    those same modules in full. Until this enum existed, the difference was
    expressed only by which sections happened to be registered, which is a
    difference the platform could not be told about.

    It belongs on Project, not Product — see the P17 build-log entry.
    """

    MULTISOURCE_GENERIC = "multisource-generic"
    NEW_CHEMICAL_ENTITY = "new-chemical-entity"


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


class PackagingRole(str, enum.Enum):
    """WHICH material a packaging row describes — the finished product, or
    the drug substance as it is shipped and stored (P19).

    WHY this had to exist before 3.2.S.6 and 3.2.P.7 could both be built:
    they are the same question asked about two different materials. An API
    travels in a fibre drum with a double LDPE liner; the tablets travel in
    an alu/PVC blister inside a printed carton. One `Packaging` model with
    no role would have answered both leaves with the same rows, which is
    not an approximation of the truth -- it is a container closure system
    filed against a material it was never qualified for.

    Nothing infers this from `component`: a PRIMARY pack is primary for
    whatever it holds, and the drum is as primary to the API as the blister
    is to the tablet.
    """

    DRUG_PRODUCT = "drug product"
    DRUG_SUBSTANCE = "drug substance"


class PackagingComponent(str, enum.Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    ARTWORK = "artwork"
    LABEL = "label"
    LEAFLET = "leaflet"
    CARTON = "carton"


class ExcipientOrigin(str, enum.Enum):
    """Where an excipient's material comes from (P19).

    Exists for one leaf and one rule: 3.2.P.4.5 "Excipients of human or
    animal origin" is a TSE/BSE statement, and it cannot be generated from
    a list of excipient names -- lactose (bovine milk), gelatin (bovine or
    porcine hide/bone) and magnesium stearate (which may be vegetable OR
    animal) are indistinguishable by name. The filer has to say.

    None (the column is nullable) means NOT STATED, which is different from
    SYNTHETIC: rule R21 can only speak about what has been declared, and a
    statement covering an excipient nobody classified would be a claim the
    filer never made.
    """

    SYNTHETIC = "synthetic"
    MINERAL = "mineral"
    PLANT = "plant"
    ANIMAL = "animal"
    HUMAN = "human"


# The origins that put an excipient inside the scope of the TSE/BSE
# statement at 3.2.P.4.5 -- and so of rule R21. Single source of truth so
# the rule and the rendered statement cannot disagree about which
# excipients they are talking about.
TSE_RELEVANT_ORIGINS = frozenset({ExcipientOrigin.ANIMAL, ExcipientOrigin.HUMAN})


class StabilityStudyType(str, enum.Enum):
    ACCELERATED = "accelerated"
    LONG_TERM = "long-term"
    INTERMEDIATE = "intermediate"


class BEStudyDesign(str, enum.Enum):
    """How the bioequivalence study was laid out.

    A crossover gives every subject both formulations with a washout
    between, so each subject is their own control -- which is why it is the
    default design for an ordinary immediate-release generic and why far
    fewer subjects are needed. A parallel design is what you fall back to
    when the drug's half-life makes a washout impractical (or the
    comparison is in patients), and it costs statistical power. Replicate
    designs dose one or both formulations twice, and exist to estimate
    within-subject variability -- the evidence a highly-variable drug needs
    before a widened acceptance window can be argued for at all.
    """

    CROSSOVER = "crossover"
    PARALLEL = "parallel"
    REPLICATE_CROSSOVER = "replicate crossover"


class BEFedState(str, enum.Enum):
    """Fasting or fed. Not a detail: for a product whose label requires
    administration with food, a fasting study answers a question nobody
    asked, and for a modified-release product an agency generally wants
    both."""

    FASTING = "fasting"
    FED = "fed"


class BEDoseRegimen(str, enum.Enum):
    SINGLE_DOSE = "single dose"
    MULTIPLE_DOSE = "multiple dose"


class PKParameter(str, enum.Enum):
    """The pharmacokinetic parameters a bioequivalence conclusion rests on.

    Cmax is the peak concentration -- the rate of absorption. AUC is the
    area under the concentration-time curve -- the extent of absorption,
    measured both to the last quantifiable timepoint (0-t) and extrapolated
    to infinity (0-inf). An agency reads the 90 % confidence interval of
    the test/reference ratio for each of these, and all of them have to sit
    inside the acceptance window; passing on two out of three is not a
    partial result, it is a failed study.

    Spelled as the pharmacopoeial shorthand rather than a code, because
    this string is PRINTED on the BTI form (1.4.1) and in the tabular
    listing (5.2), where an assessor expects to read "AUC(0-t)".
    """

    CMAX = "Cmax"
    AUC_0_T = "AUC(0-t)"
    AUC_0_INF = "AUC(0-inf)"


class BiowaiverKind(str, enum.Enum):
    """The two ways a multisource filing avoids an in vivo study.

    A BCS-based biowaiver (leaf 1.2.17) argues from the Biopharmaceutics
    Classification System: a highly soluble, highly permeable drug in a
    rapidly dissolving immediate-release product does not need a human
    study to prove it behaves like the comparator. An additional-strength
    biowaiver (leaf 1.2.18) argues from proportionality: the study was run
    at one strength, and the other strengths are compositionally
    proportional with similar dissolution profiles.
    """

    BCS_BASED = "BCS-based"
    ADDITIONAL_STRENGTH = "additional strength"


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
    TRADEMARK = "trademark-registration"  # product-level, not site-specific
    MANUFACTURING_LICENCE = "manufacturing-licence"  # site-specific, like GMP
    # P18: found by checking the enum against the target TOC rather than
    # against intuition. All three are ordinary NAFDAC Module 1 requirements
    # about the APPLICANT as a business rather than about the medicine --
    # which is exactly why a list written while thinking about product
    # quality missed them.
    INCORPORATION = "certificate-of-incorporation"  # 1.2.3, the company itself
    PHARMACIST_LICENCE = "superintendent-pharmacist-licence"  # 1.2.11, annual
    PREMISES_REGISTRATION = "premises-registration"  # 1.2.12, the site's own
    # P19: the supplier's declaration that a material of animal origin is
    # sourced and processed so as to be free of TSE/BSE risk. It is a
    # CERTIFICATE and not a declaration for the ordinary reason -- the
    # applicant cannot write it, the material's supplier must.
    TSE_BSE = "tse-bse-certificate"


class DeclarationType(str, enum.Enum):
    """A Module 1 administrative document whose CONTENT we can generate
    from data on file (unlike a Certificate, which only a third party can
    issue) but which still needs a human signature -- and, for some types,
    notarization/legalization -- before it's real. See
    app.templating.declarations for the "SIGNATURE REQUIRED" placeholder
    this becomes at assembly time."""

    POWER_OF_ATTORNEY = "power-of-attorney"  # appoints the local representative
    DECLARATION_OF_AUTHENTICITY = "declaration-of-authenticity"
    GMP_COMPLIANCE_UNDERTAKING = "gmp-compliance-undertaking"


# Which declaration types need a notary/legalization on top of a plain
# signature -- a Power of Attorney and a GMP undertaking are typically
# notarized/legalized in a NAFDAC filing, while a Declaration of
# Authenticity is usually just signed. Single source of truth so
# app.templating.declarations's placeholder text and P06's R15 rule can't
# drift out of sync with each other.
DECLARATIONS_REQUIRING_NOTARIZATION = frozenset(
    {DeclarationType.POWER_OF_ATTORNEY, DeclarationType.GMP_COMPLIANCE_UNDERTAKING}
)


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


class UserRole(str, enum.Enum):
    """Access level, not dossier content -- lives here anyway since this is
    the project's one place enums live (see module WHY), same as
    NarrativeStatus above. USER can only ever reach data it owns (see
    Product.owner_id's WHY); ADMIN additionally reaches app.api.routers.admin
    -- account management, never a bypass of the ownership check itself."""

    USER = "user"
    ADMIN = "admin"


class SpecificationOwnerKind(str, enum.Enum):
    """WHAT a specification (or a batch of it) is about.

    A specification is one artifact -- a list of tests, each with a method
    and an acceptance criterion -- and the CTD asks for it three times, of
    three different things: 3.2.S.4.1 of the drug substance, 3.2.P.4.1 of
    each excipient, 3.2.P.5.1 of the finished product. This enum is not a
    stored column anywhere; it is the NAME of the answer that
    `SpecificationTest.owner_kind` derives from which foreign key is set
    (see app/models/spec_owner.py for why the owner is three nullable FKs
    rather than a stored discriminator). It exists so the API, the wizard
    and the rules can talk about the owner type without each inventing its
    own three strings.
    """

    DRUG_SUBSTANCE = "drug-substance"
    DRUG_PRODUCT = "drug-product"
    EXCIPIENT = "excipient"


class ImpurityType(str, enum.Enum):
    """Where an impurity COMES FROM, which is the distinction ICH Q3A/Q3B
    is built on and the one 3.2.S.3.2 and 3.2.P.5.5 are organised by.

    The difference is not cosmetic: a process-related impurity is
    controlled by the drug substance's specification and its route of
    synthesis, and a degradation product is controlled by the finished
    product's specification, its packaging and its shelf life. Filing one
    as the other points an assessor at the wrong control strategy.

    DEGRADATION covers Q3B's "degradation product" (and, on the substance
    side, a degradant seen on the API's own stability). RESIDUAL_SOLVENT is
    kept separate because ICH Q3C sets its limits by class, independently
    of Q3A -- rule R10 already reads those class limits, and a solvent
    filed as a process impurity would be checked against the wrong table.
    """

    PROCESS_RELATED = "process-related"
    DEGRADATION = "degradation"
    RESIDUAL_SOLVENT = "residual-solvent"
    INORGANIC = "inorganic"
