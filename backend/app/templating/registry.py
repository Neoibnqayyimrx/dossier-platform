"""Section registry for the real docxtpl template engine (P04).

This is the successor to the Markdown prototype in `section_map.py` (kept
as-is — `render_p1` there still backs `test_rendered_section_cannot_contain_
bugs` and `run_demo.py`, which predate this module and test a different
concern: that the rule engine catches real LAMOX copy-paste bugs, not the
template engine itself).

WHY a typed dataclass registry instead of a plain dict of strings: P07/P08
will iterate over every registered section to assemble a full dossier, and
need to know, for each one, which template file to load and which narrative
slots P05 is allowed to fill. Encoding that as fields on `SectionSpec` means
"what sections exist and what they need" lives in one typed place, not
scattered across context.py's per-section branches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


@dataclass(frozen=True)
class SectionSpec:
    number: str
    title: str
    template_filename: str
    narrative_slots: list[str] = field(default_factory=list)
    # P05: what to search the P03 knowledge base for when grounding this
    # section's narrative. A deliberate, hand-written query per section —
    # not just reusing `title` verbatim — so retrieval targets what the
    # narrative actually needs to say, not just what the section is called.
    grounding_query: str | None = None

    @property
    def template_path(self) -> Path:
        return TEMPLATES_DIR / self.template_filename


SECTIONS: dict[str, SectionSpec] = {
    "1.0": SectionSpec(
        number="1.0",
        title="Cover Letter",
        template_filename="cover_letter.docx",
        narrative_slots=["purpose"],
        grounding_query="administrative submission requirements cover letter",
    ),
    "3.2.P.1": SectionSpec(
        number="3.2.P.1",
        title="Description and Composition of Drug Product",
        template_filename="section_3_2_p_1.docx",
        narrative_slots=["description"],
        grounding_query="description and composition of the drug product dosage form",
    ),
    "3.2.P.8.1": SectionSpec(
        number="3.2.P.8.1",
        title="Stability Summary and Conclusion",
        template_filename="stability_summary.docx",
        narrative_slots=["conclusion"],
        grounding_query="stability testing storage conditions retest period shelf life",
    ),
}


def get_section(number: str) -> SectionSpec:
    try:
        return SECTIONS[number]
    except KeyError:
        raise KeyError(
            f"No registered section {number!r}; registered sections: " f"{', '.join(SECTIONS)}"
        )
