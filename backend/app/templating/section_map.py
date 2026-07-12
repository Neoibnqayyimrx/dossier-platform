"""Template engine (P04) — minimal, runnable version.

Demonstrates the key idea: DATA SLOTS are filled deterministically from the
model; the composition TABLE is built from BatchFormulaLine rows, never typed
as prose. A NARRATIVE SLOT is left for approved LLM text (P05).

In the full platform this is a docxtpl .docx template producing Word output.
Here it renders Markdown so the slice runs with no binary tooling — the
separation of concerns is identical.
"""

from __future__ import annotations

from jinja2 import Template

# Registry mapping section number -> (title, template, narrative slots)
SECTION_MAP = {
    "3.2.P.1": {
        "title": "Description and Composition of Drug Product",
        "narrative_slots": ["description"],
    },
}

_P1_TEMPLATE = Template("""## 3.2.P.1 {{ title }}

**Product:** {{ product.brand_name }} — {{ product.generic_name }}
{{ '%0.0f'|format(product.strength_value|float) }} {{ product.strength_unit }} {{ product.dosage_form.value }}

**Description:** {{ narrative.description or '<<AI WRITES ONLY THIS — draft not approved>>' }}

**Composition (per unit / per batch of {{ batch_size }} units):**

| Component | Spec | Qty/unit (mg) | Batch qty |
|---|---|---|---|
{% for line in batch_formula -%}
| {{ line.component }} | {{ line.spec }} | {{ '%0.2f'|format(line.qty_per_unit_mg|float) }} | {{ line.declared_batch_qty_kg and ('%0.2f kg'|format(line.declared_batch_qty_kg|float)) or '' }} |
{% endfor %}
""")


def render_p1(product, narrative: dict | None = None) -> str:
    """Render 3.2.P.1 from structured data. Note: the strength and the table
    come from the MODEL, so this rendered output physically cannot contain the
    '250mg'/'Tablets' bugs — that's the determinism boundary in action."""
    batch_size = product.batch_formula[0].batch_size_units if product.batch_formula else 0
    return _P1_TEMPLATE.render(
        title=SECTION_MAP["3.2.P.1"]["title"],
        product=product,
        batch_formula=product.batch_formula,
        batch_size=batch_size,
        narrative=narrative or {},
    )
