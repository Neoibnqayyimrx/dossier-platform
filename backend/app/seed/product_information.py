"""SmPC clinical particulars for the seeds (P23).

WHY this is its own module, like `specifications.py` and `stability.py`
before it: three hand-written copies of the same eleven sections would
drift, and what the fixtures demonstrate is the SHAPE -- one column per
numbered SmPC section, a structured list where the guideline asks for a
list -- not the wording.

## What is NOT here, and why that is the demonstration

There is no shelf life, no storage condition, no strength and no pack size
anywhere in this file. The seeded products already carry all four
(`build_examox` sets `shelf_life_months=24` and a storage statement), and
the SmPC, the label and the leaflet all read them from there at render
time. If a seed could set them here, the fixture would be modelling the
defect rather than the fix.

## The planted defect

`attach_product_information(product, buggy=True)` writes the SmPC content
for AMPICLOX's buggy variant, and plants one thing: a batch formula line
(`Colloidal Silicon Dioxide`) with no matching excipient row, so the
glidant is manufactured into every capsule and appears in NEITHER SmPC 6.1
NOR the patient leaflet.

That is rule R28's ERROR, and it is the ordinary version of this defect: a
formulation change adds a glidant to improve flow, 3.2.P.3.2 is updated
because that is what the production department maintains, and the
patient-facing documents are never touched. A patient with an intolerance
reads the leaflet.

The wording throughout is illustrative, not medical advice, and it is
generic-appropriate: an amoxicillin SmPC's clinical particulars are the
innovator's, restated.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import AdverseEventFrequency, BatchFormulaLine, ProductInformation


@dataclass(frozen=True)
class ClassParticulars:
    """The SmPC sections that belong to a PHARMACOLOGICAL CLASS rather than
    to one product (P24e).

    WHY this was extracted: until P24 every fixture was a beta-lactam, so
    the penicillin contraindications, warnings and adverse effects could sit
    in the function as constants. P24's Amlodipine worked example is a
    dihydropyridine calcium-channel blocker, and reusing that block would
    have filed an SmPC warning a patient about penicillin allergy on a
    cardiovascular product.

    That is not a cosmetic problem with a fixture. The whole demonstration
    is that these documents cannot say something the data does not support,
    and a worked example whose own clinical particulars are for a different
    drug class would undercut it on the first page a pharmacist read.

    Indications and posology stay per-PRODUCT arguments: those differ
    between two products of the same class, which the rest of this does not.
    """

    contraindications: list[str]
    warnings: list[str]
    effects: list[dict]
    interactions: str
    pregnancy_and_lactation: str
    effects_on_driving: str
    overdose: str


# The penicillin clinical particulars, shared by all three fixtures --
# EXAMOX and LAMOX are amoxicillin, AMPICLOX is ampicillin + cloxacillin,
# and their contraindications and warnings are the beta-lactam class's.
_PENICILLIN_CONTRAINDICATIONS = [
    "You are allergic to penicillins or to any of the other ingredients of this medicine.",
    "You have ever had a severe allergic reaction to a cephalosporin, carbapenem or "
    "monobactam antibiotic.",
    "You have ever had jaundice or a liver problem after taking this medicine before.",
]

_PENICILLIN_WARNINGS = [
    "You have ever had an allergic reaction to any antibiotic.",
    "You have kidney problems, because the dose may need to be lowered.",
    "You have glandular fever (infectious mononucleosis), because a rash is more likely.",
    "You are taking a medicine that thins the blood, such as warfarin.",
    "You get severe or watery diarrhoea during or after treatment.",
]

_PENICILLIN_EFFECTS = [
    {"effect": "Diarrhoea", "frequency": AdverseEventFrequency.COMMON.value},
    {"effect": "Feeling sick (nausea)", "frequency": AdverseEventFrequency.COMMON.value},
    {"effect": "Skin rash", "frequency": AdverseEventFrequency.COMMON.value},
    {"effect": "Being sick (vomiting)", "frequency": AdverseEventFrequency.UNCOMMON.value},
    {"effect": "Thrush (a fungal infection)", "frequency": AdverseEventFrequency.UNCOMMON.value},
    {
        "effect": "A severe allergic reaction with swelling of the face or throat",
        "frequency": AdverseEventFrequency.RARE.value,
    },
    {
        "effect": "Inflammation of the large bowel with severe diarrhoea",
        "frequency": AdverseEventFrequency.VERY_RARE.value,
    },
]


PENICILLIN = ClassParticulars(
    contraindications=list(_PENICILLIN_CONTRAINDICATIONS),
    warnings=list(_PENICILLIN_WARNINGS),
    effects=[dict(effect) for effect in _PENICILLIN_EFFECTS],
    interactions=(
        "Tell your doctor if you are taking allopurinol, probenecid, methotrexate "
        "or a medicine that thins the blood such as warfarin. This medicine may "
        "also make the oral contraceptive pill less reliable."
    ),
    pregnancy_and_lactation=(
        "Ask your doctor or pharmacist for advice before taking this medicine if "
        "you are pregnant, think you may be pregnant or are breast-feeding. "
        "Penicillins are generally considered suitable in pregnancy, but only "
        "your doctor can decide."
    ),
    effects_on_driving=(
        "This medicine is not expected to affect your ability to drive or use "
        "machines. Very rarely it can cause dizziness or a fit; do not drive if "
        "this happens to you."
    ),
    overdose=(
        "If you take more of this medicine than you should, contact your doctor "
        "or nearest hospital straight away and take the pack with you. Too much "
        "may cause an upset stomach or, rarely, crystals in the urine."
    ),
)


# P24e: the dihydropyridine calcium-channel blockers, for the Amlodipine
# worked example. Illustrative wording, generic-appropriate -- a generic's
# clinical particulars are the innovator's, restated -- and written in the
# patient register the leaflet is judged in (rule R33).
DIHYDROPYRIDINE = ClassParticulars(
    contraindications=[
        "You are allergic to amlodipine, to other medicines like it (called "
        "dihydropyridines), or to any of the other ingredients of this medicine.",
        "You have very low blood pressure.",
        "You have a narrowing of the main valve of the heart (aortic stenosis) or "
        "shock caused by your heart not pumping properly.",
        "You have heart failure after a heart attack.",
    ],
    warnings=[
        "You have recently had a heart attack, or you have heart failure.",
        "You have liver problems, because your doctor may start you on a lower dose.",
        "Your blood pressure rises or falls a lot.",
        "You are elderly, because any increase in your dose will be made carefully.",
        "Your gums become swollen or tender; tell your dentist that you take this " "medicine.",
    ],
    effects=[
        {"effect": "Swollen ankles (oedema)", "frequency": AdverseEventFrequency.COMMON.value},
        {"effect": "Headache", "frequency": AdverseEventFrequency.COMMON.value},
        {"effect": "Dizziness", "frequency": AdverseEventFrequency.COMMON.value},
        {"effect": "Flushing", "frequency": AdverseEventFrequency.COMMON.value},
        {"effect": "Feeling very tired", "frequency": AdverseEventFrequency.COMMON.value},
        {
            "effect": "Fast or irregular heartbeat (palpitations)",
            "frequency": AdverseEventFrequency.UNCOMMON.value,
        },
        {"effect": "Swollen or tender gums", "frequency": AdverseEventFrequency.RARE.value},
        {
            "effect": "A severe allergic reaction with swelling of the face or throat",
            "frequency": AdverseEventFrequency.VERY_RARE.value,
        },
    ],
    interactions=(
        "Tell your doctor if you are taking any other medicine for blood pressure, "
        "a medicine for a fungal infection such as ketoconazole or itraconazole, "
        "rifampicin, ritonavir, ciclosporin, simvastatin, or the herbal remedy St "
        "John's wort. Do not drink grapefruit juice while taking this medicine, "
        "because it can raise the amount of the medicine in your blood."
    ),
    pregnancy_and_lactation=(
        "Tell your doctor if you are pregnant, think you may be pregnant or are "
        "breast-feeding. The safety of this medicine in pregnancy has not been "
        "established, and small amounts pass into breast milk, so your doctor will "
        "decide whether you should take it."
    ),
    effects_on_driving=(
        "This medicine can make some people feel dizzy, sick or tired, or give them "
        "a headache. If it affects you this way, do not drive or use tools or "
        "machines."
    ),
    overdose=(
        "If you take more of this medicine than you should, contact your doctor or "
        "nearest hospital straight away and take the pack with you. Too much can "
        "make your blood pressure fall dangerously low; you should be lying down "
        "with your legs raised while you wait for help."
    ),
)


def attach_product_information(
    product,
    *,
    indications: str,
    posology: str,
    particulars: ClassParticulars = PENICILLIN,
    buggy: bool = False,
) -> ProductInformation:
    """Give `product` its SmPC clinical particulars.

    `indications` and `posology` are per-product because they are the only
    two sections where two products of the SAME class genuinely say
    different things -- a broad-spectrum penicillin and a fixed-dose
    combination of two of them. Everything else is the class's, which is
    why it arrives as a `ClassParticulars` rather than being retyped per
    fixture.

    `particulars` defaults to PENICILLIN so the three beta-lactam fixtures
    are unchanged; P24e's Amlodipine passes DIHYDROPYRIDINE.

    `buggy=True` plants R28's defect -- see this module's docstring.
    """
    information = ProductInformation(
        therapeutic_indications=indications,
        posology_and_administration=posology,
        contraindications=list(particulars.contraindications),
        special_warnings=list(particulars.warnings),
        interactions=particulars.interactions,
        pregnancy_and_lactation=particulars.pregnancy_and_lactation,
        effects_on_driving=particulars.effects_on_driving,
        undesirable_effects=[dict(effect) for effect in particulars.effects],
        overdose=particulars.overdose,
        incompatibilities=(
            "Not applicable to this presentation. The product is supplied ready to "
            "take and is not reconstituted or mixed before use."
        ),
        special_precautions_for_disposal=(
            "Do not throw away any medicines via wastewater or household waste. Ask "
            "your pharmacist how to throw away medicines you no longer use. These "
            "measures will help protect the environment."
        ),
    )
    product.product_information = information

    if buggy:
        # The planted R28 defect, and note HOW it has to be planted: by
        # putting a real component into the batch formula, not by typing a
        # wrong list into the SmPC. SmPC 6.1 and the leaflet both render
        # from `product.excipients`, so there is no field anywhere that
        # could hold a divergent excipient list -- even a fixture trying to
        # create this defect has to create a genuine disagreement between
        # two real tables. That constraint is the phase.
        product.batch_formula.append(
            BatchFormulaLine(
                component="Colloidal Silicon Dioxide",
                spec="BP",
                qty_per_unit_mg=4.0,
                batch_size_units=100_000,
                declared_batch_qty_kg=0.4,
            )
        )
    return information
