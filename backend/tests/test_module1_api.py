"""P15a: the Module 1 entities, and the export they unblock.

Before this phase a NAFDAC dossier could not be completed through the API
at all. Applicant, Certificate and Declaration had models and document
renderers but no schemas, routers or UI, so R13/R14/R16 blocked every
build and the only way past them was a validation override -- which is
supposed to be a deliberate exception, not the normal route to an export.

The last test here is the phase's definition of done, written as an
assertion: a complete NAFDAC filing assembled entirely through HTTP,
reaching `is_exportable` with NO overrides logged.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.seed.documents import MINIMAL_PDF


async def _complete_nafdac_project(client) -> dict:
    """Every fact the NAFDAC rule set asks for, entered the way the wizard
    enters it -- one API call per collection, nothing seeded behind the
    API's back."""
    product = (
        await client.post(
            "/products",
            json={
                "brand_name": "FULLMOX",
                "generic_name": "Amoxicillin",
                "dosage_form": "hard gelatin capsule",
                "route_of_administration": "oral",
                "shelf_life_months": 24,
                "storage_condition": "Store below 30 C. Protect from light.",
                "pack_size": "10 x 10 blister",
                "legal_status": "prescription-only",
                "registration_type": "new",
                "country": "Nigeria",
                # P22/R26: the comparator the APPLICATION declares, printed
                # at 1.2 and 2.3. The study below names its own, and the
                # rule refuses to let the two disagree -- so both have to
                # be entered, exactly as a real filer enters them.
                "reference_product_name": "Amoxil 500 mg capsules",
                "reference_product_manufacturer": "Innovator Pharmaceuticals Ltd",
            },
        )
    ).json()
    product_id = product["id"]

    # R17 wants the drug substance's own manufacturer, and R09 wants that
    # site to actually play the API-manufacturer role -- pointing an active
    # at the finished-product site is the mistake it exists to catch.
    api_site = (
        await client.post(
            f"/products/{product_id}/manufacturers",
            json={
                "name": "Exagon API Plant",
                "role": "API manufacturer",
                "country": "Nigeria",
                "gmp_status": "certified",
            },
        )
    ).json()
    await client.post(
        f"/products/{product_id}/manufacturers",
        json={
            "name": "Exagon Ltd",
            "role": "finished product",
            "country": "Nigeria",
            "gmp_status": "certified",
        },
    )

    ingredient = (
        await client.post(
            f"/products/{product_id}/apis",
            json={
                "inn_name": "Amoxicillin",
                "strength_value": 500,
                "strength_unit": "mg",
                "salt_form": "Amoxicillin Trihydrate",
                "salt_factor": 1.15,
                "compendial_std": "BP",
                "manufacturer_id": api_site["id"],
            },
        )
    ).json()

    # R07: a drug substance needs a specification table, not a free-text note.
    await client.post(
        f"/apis/{ingredient['id']}/specification",
        json={
            "test_name": "Assay",
            "method": "HPLC (BP)",
            "acceptance_criterion": "95.0-105.0 %",
        },
    )

    # R05: the declared shelf life must be covered by long-term data.
    #
    # P21 removed `result_summary` from the wire. A study with no timepoint
    # results on file falls back to its declared duration, which is exactly
    # the pre-P21 behaviour and is what this fixture is exercising -- the
    # point here is the Module 1 path, not the stability data.
    await client.post(
        f"/products/{product_id}/stability",
        json={
            "study_type": "long-term",
            "duration_months": 24,
            "condition": "30 C / 75 % RH",
        },
    )

    # R12 compares the declared pack size against artwork/label/carton text.
    await client.post(
        f"/products/{product_id}/packaging",
        json={
            "component": "carton",
            "description": "Printed carton, 10 x 10 blister",
            "material": "Duplex board",
        },
    )

    # R06: a multisource filing has to take exactly one bioequivalence
    # route, and P22 made that route real data rather than a row of prose.
    #
    # Three calls, because the shape of the evidence is three things: the
    # comparator is its own row (two studies routinely dose the same batch,
    # and 1.4.1 prints its batch and expiry), the study points at it, and
    # the confidence intervals go up as a SET -- a study holding two of its
    # three intervals is worse than one holding none, because it looks
    # answered.
    comparator = (
        await client.post(
            f"/products/{product_id}/reference-products",
            json={
                "name": "Amoxil 500 mg capsules",
                "manufacturer": "Innovator Pharmaceuticals Ltd",
                "strength": "500 mg",
                "country_of_origin": "United Kingdom",
                "batch_number": "REF/24/1180",
                "expiry_date": str(date.today() + timedelta(days=365)),
            },
        )
    ).json()
    study = (
        await client.post(
            f"/products/{product_id}/bioequivalence",
            json={
                "study_identifier": "FULLMOX/BE/2025-01",
                "design": "crossover",
                "fed_state": "fasting",
                "dose_regimen": "single dose",
                "subjects_enrolled": 36,
                "subjects_completed": 34,
                "analyte": "Amoxicillin in human plasma",
                "cro_name": "Accord Clinical Research Ltd",
                "reference_product_id": comparator["id"],
            },
        )
    ).json()
    await client.put(
        f"/bioequivalence/{study['id']}/results",
        json=[
            {"parameter": "Cmax", "ci_lower": "91.30", "ci_upper": "106.10"},
            {"parameter": "AUC(0-t)", "ci_lower": "95.80", "ci_upper": "106.80"},
            {"parameter": "AUC(0-inf)", "ci_lower": "95.40", "ci_upper": "106.70"},
        ],
    )

    # R13: a CPP that is on file AND unexpired -- the date matters, not
    # merely the row (an expired CPP is its own finding).
    await client.post(
        f"/products/{product_id}/certificates",
        json={
            "certificate_type": "CPP",
            "issuing_authority": "NAFDAC",
            "certificate_number": "CPP-2026-001",
            "issue_date": str(date.today() - timedelta(days=30)),
            "expiry_date": str(date.today() + timedelta(days=365)),
        },
    )

    # R14: who is legally filing.
    applicant = (
        await client.post(
            "/applicants",
            json={
                "company_name": "Exagon Pharmaceuticals Ltd",
                "address": "Cadastral Zone, Gwagwalada, Abuja",
                "country": "Nigeria",
                "contact_name": "Aisha Bello",
                "contact_email": "regulatory@exagon.example",
                "authorized_representative_name": "Aisha Bello",
                "authorized_representative_title": "Head of Regulatory Affairs",
            },
        )
    ).json()

    project = (
        await client.post(
            "/projects",
            json={
                "name": "FULLMOX new registration",
                "region": "NAFDAC",
                "product_id": product_id,
                "applicant_id": applicant["id"],
            },
        )
    ).json()

    # R16 wants both of these present, R15 wants them signed.
    for declaration_type in ("power-of-attorney", "declaration-of-authenticity"):
        await client.post(
            f"/projects/{project['id']}/declarations",
            json={
                "declaration_type": declaration_type,
                "signed": True,
                "signed_date": str(date.today()),
                "notarized": True,
                "notarization_date": str(date.today()),
            },
        )

    # P18: R20 wants the CPP itself, not merely the row saying one is
    # expected. This is the last step of a real filing and the one the
    # platform could not do at all before this phase -- and it happens here,
    # through the same HTTP API as everything else, which is what makes this
    # test's claim ("no seeding, nothing behind the API's back") still true.
    await client.put(
        f"/projects/{project['id']}/documents/1.2.7",
        files={"file": ("CPP_NAFDAC.pdf", MINIMAL_PDF, "application/pdf")},
    )

    # P23: R30 blocks on the three clinical particulars that ARE the
    # authorisation -- 4.1 indications, 4.2 posology, 4.3 contraindications.
    # They live nowhere else in the data model, so unlike every other fact
    # in the SmPC they cannot be derived; an empty 4.3 yields a well-formed
    # document with no contraindications section, which looks finished and
    # is not. This test predates the rule, which is why it failed at HEAD.
    # Completed here through the same API as everything else rather than by
    # relaxing the assertion, because "no seeding, nothing behind the API's
    # back" is the claim the test exists to make.
    product_information = await client.put(
        f"/products/{product_id}/product-information",
        json={
            "therapeutic_indications": (
                "Treatment of susceptible bacterial infections of the respiratory "
                "tract, urinary tract, skin and soft tissue in adults and children."
            ),
            "posology_and_administration": (
                "Adults and children over 12 years: one capsule every eight hours. "
                "Swallow whole with water. Duration as directed by the prescriber."
            ),
            # A list, not prose: 4.3 is rendered as discrete entries in the
            # SmPC, the label and the leaflet alike (P23).
            "contraindications": [
                "Hypersensitivity to penicillins, cephalosporins or to any of the "
                "excipients listed in section 6.1.",
                "History of a severe immediate hypersensitivity reaction to any "
                "beta-lactam agent.",
            ],
        },
    )
    # A setup step that fails silently is how a test ends up asserting
    # something it never actually set up.
    assert product_information.status_code == 200, product_information.text

    return {"product_id": product_id, "project_id": project["id"], "applicant_id": applicant["id"]}


async def _errors(client, project_id: str) -> list[str]:
    readiness = (await client.get(f"/projects/{project_id}/readiness")).json()
    return [f["rule_id"] for f in readiness["findings"] if f["severity"] == "ERROR"]


# ---- each blocker, cleared through its own endpoint --------------------------


async def test_applicant_clears_r14(auth_client):
    ids = await _complete_nafdac_project(auth_client)
    assert "R14" not in await _errors(auth_client, ids["project_id"])

    # And it comes back on the project, so the UI can show who is filing
    # without a second round-trip.
    project = (await auth_client.get(f"/projects/{ids['project_id']}")).json()
    assert project["applicant"]["company_name"] == "Exagon Pharmaceuticals Ltd"


async def test_cpp_certificate_clears_r13(auth_client):
    ids = await _complete_nafdac_project(auth_client)
    assert "R13" not in await _errors(auth_client, ids["project_id"])


async def test_an_expired_cpp_still_blocks(auth_client):
    """R13 checks the date, not the row -- a filing cannot be cleared by
    recording a certificate that has run out."""
    ids = await _complete_nafdac_project(auth_client)
    certificates = (await auth_client.get(f"/products/{ids['product_id']}/certificates")).json()
    await auth_client.patch(
        f"/products/{ids['product_id']}/certificates/{certificates[0]['id']}",
        json={"expiry_date": str(date.today() - timedelta(days=1))},
    )
    assert "R13" in await _errors(auth_client, ids["project_id"])


async def test_declarations_clear_r16(auth_client):
    ids = await _complete_nafdac_project(auth_client)
    assert "R16" not in await _errors(auth_client, ids["project_id"])

    project = (await auth_client.get(f"/projects/{ids['project_id']}")).json()
    assert {d["declaration_type"] for d in project["declarations"]} == {
        "power-of-attorney",
        "declaration-of-authenticity",
    }


async def test_an_unsigned_declaration_still_blocks(auth_client):
    """R15's point: an unsigned declaration is worse than a missing one,
    because the document exists and looks complete."""
    ids = await _complete_nafdac_project(auth_client)
    declarations = (await auth_client.get(f"/projects/{ids['project_id']}/declarations")).json()
    await auth_client.patch(
        f"/projects/{ids['project_id']}/declarations/{declarations[0]['id']}",
        json={"signed": False},
    )
    assert "R15" in await _errors(auth_client, ids["project_id"])


# ---- the definition of done --------------------------------------------------


async def test_a_nafdac_dossier_reaches_exportable_through_the_api_alone(auth_client):
    """No seeding, no overrides: every fact entered through the HTTP API the
    wizard uses, and the export gate opens on its own."""
    ids = await _complete_nafdac_project(auth_client)

    readiness = (await auth_client.get(f"/projects/{ids['project_id']}/readiness")).json()
    blocking = [f for f in readiness["findings"] if f["severity"] == "ERROR"]
    assert blocking == [], blocking
    assert readiness["is_exportable"] is True
    assert readiness["overridden_rule_ids"] == []
