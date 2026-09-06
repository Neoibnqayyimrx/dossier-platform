/**
 * The wizard's shape, as data.
 *
 * WHY field specs instead of six hand-written forms: the backend builds
 * all six Product-child routers from ONE factory
 * (app/api/routers/product_children.py) because they genuinely are the
 * same resource shape with different fields. Mirroring that here means
 * adding a field is a one-line edit in this file, and adding a whole
 * collection is one more entry -- not another bespoke form component that
 * drifts from its five siblings.
 *
 * `vocabulary` names a key from GET /enums. Nothing in this file hard-codes
 * an option list; that is the point (see app/api/routers/enums.py).
 */

import type { ProductChildResource } from "@/lib/api";

/**
 * The two vocabularies the wizard builds at RUNTIME from rows you have
 * already saved, rather than fetching from /enums: an active ingredient
 * names its manufacturer, a batch-formula line names its active. Declared
 * here so the field specs and the wizard that fills them cannot drift on
 * a spelling -- a typo in either place is a select that silently offers
 * nothing.
 */
export const RUNTIME_VOCABULARIES = ["manufacturer", "active_ingredient"] as const;

export type RuntimeVocabulary = (typeof RUNTIME_VOCABULARIES)[number];

export interface FieldSpec {
  name: string;
  label: string;
  type: "text" | "number" | "select" | "checkbox" | "textarea" | "date";
  /**
   * Key into the vocabularies map. Usually a controlled vocabulary from
   * GET /enums, but two are built at runtime from what you have already
   * entered in an earlier step -- "manufacturer" and "active_ingredient"
   * (see the wizard's dynamic vocabularies). A cross-reference between two
   * rows you just created cannot come from a static enum.
   */
  vocabulary?: string;
  required?: boolean;
  help?: string;
  placeholder?: string;
}

export interface ChildStepSpec {
  id: ProductChildResource;
  title: string;
  /**
   * The add-button label, written out rather than derived from `title`.
   * A `.replace(/s$/, "")` singulariser looks fine until "Stability
   * studies" becomes "Add stability studie" -- English plurals are not
   * regex-able, so the singular is data like everything else here.
   */
  addLabel: string;
  blurb: string;
  /** How one saved row is summarised in the list. */
  summarise: (row: Record<string, unknown>) => string;
  fields: FieldSpec[];
}

export const PRODUCT_FIELDS: FieldSpec[] = [
  { name: "brand_name", label: "Brand name", type: "text", required: true },
  {
    name: "generic_name",
    label: "Generic name (INN)",
    type: "text",
    required: true,
  },
  { name: "dosage_form", label: "Dosage form", type: "select", vocabulary: "dosage_form" },
  {
    name: "route_of_administration",
    label: "Route of administration",
    type: "text",
    placeholder: "oral",
  },
  {
    name: "shelf_life_months",
    label: "Shelf life (months)",
    type: "number",
    help: "Cross-checked against your longest long-term stability study (rule R05).",
  },
  {
    name: "storage_condition",
    label: "Storage condition",
    type: "text",
    placeholder: "Store below 30 °C. Protect from light.",
  },
  { name: "pack_size", label: "Pack size", type: "text", placeholder: "10 x 10 blister" },
  { name: "legal_status", label: "Legal status", type: "select", vocabulary: "legal_status" },
  {
    name: "registration_type",
    label: "Registration type",
    type: "select",
    vocabulary: "registration_type",
  },
  { name: "country", label: "Country of origin", type: "text" },
];

export const CHILD_STEPS: ChildStepSpec[] = [
  {
    id: "manufacturers",
    title: "Manufacturers",
    addLabel: "Add manufacturer",
    blurb:
      "A product can list several sites in different roles — the site that makes the finished product is often not the one that makes the API.",
    summarise: (row) => `${row.name} — ${row.role}`,
    fields: [
      { name: "name", label: "Site name", type: "text", required: true },
      {
        name: "role",
        label: "Role",
        type: "select",
        vocabulary: "manufacturer_role",
        required: true,
        help: "Also decides where the site is filed: every role except “API manufacturer” gets its own copy of 3.2.P.3.1, and the API site is named in 3.2.S.2.1 instead.",
      },
      { name: "site_address", label: "Site address", type: "text" },
      { name: "country", label: "Country", type: "text" },
      {
        name: "gmp_status",
        label: "GMP status",
        type: "select",
        vocabulary: "gmp_status",
        help: "Must be certified before the dossier can be exported (rule R08).",
      },
      { name: "who_gmp", label: "WHO GMP", type: "checkbox" },
      { name: "pic_s", label: "PIC/S", type: "checkbox" },
    ],
  },
  {
    id: "apis",
    title: "Active ingredients",
    addLabel: "Add active ingredient",
    blurb:
      "Strength lives on each active ingredient, not on the product — that is what makes a combination product (e.g. ampicillin + cloxacillin) representable at all.",
    summarise: (row) =>
      [row.inn_name, row.strength_value, row.strength_unit]
        .filter(Boolean)
        .join(" "),
    fields: [
      { name: "inn_name", label: "INN name", type: "text", required: true },
      { name: "strength_value", label: "Strength", type: "number" },
      { name: "strength_unit", label: "Unit", type: "text", placeholder: "mg" },
      {
        name: "salt_form",
        label: "Salt form",
        type: "text",
        placeholder: "Amoxicillin Trihydrate",
      },
      {
        name: "salt_factor",
        label: "Salt factor",
        type: "number",
        help: "Used to check salt-to-base arithmetic in the batch formula (rule R04).",
      },
      {
        name: "compendial_std",
        label: "Compendial standard",
        type: "select",
        vocabulary: "compendial_status",
      },
      {
        name: "manufacturer_id",
        label: "Made by",
        type: "select",
        vocabulary: "manufacturer",
        help: "Required (rule R17): the eCTD backbone cannot name a drug substance without its manufacturer. Pick the API site, not the finished-product one (rule R09).",
      },
    ],
  },
  {
    id: "excipients",
    title: "Excipients",
    addLabel: "Add excipient",
    blurb: "Every non-active component of the formulation.",
    summarise: (row) =>
      [row.name, row.function].filter(Boolean).join(" — "),
    fields: [
      { name: "name", label: "Name", type: "text", required: true },
      {
        name: "function",
        label: "Function",
        type: "select",
        vocabulary: "excipient_function",
      },
      { name: "grade", label: "Grade", type: "text" },
      { name: "supplier", label: "Supplier", type: "text" },
      {
        name: "compendial_status",
        label: "Compendial status",
        type: "select",
        vocabulary: "compendial_status",
      },
      {
        name: "origin",
        label: "Origin",
        type: "select",
        vocabulary: "excipient_origin",
        help: "Generates the TSE/BSE statement at 3.2.P.4.5. An excipient of animal or human origin needs a TSE/BSE certificate on file (rule R21) — and the name never tells you: magnesium stearate is vegetable in one plant and tallow-derived in the next.",
      },
    ],
  },
  {
    id: "packaging",
    title: "Packaging",
    addLabel: "Add packaging component",
    blurb:
      "Primary, secondary and labelling components — for the finished product, and for the drug substance as it arrives. Checked for consistency against the declared pack size (rule R12).",
    // The role leads the summary because it is what tells two otherwise
    // similar rows apart: "primary — Alu/PVC blister" and "primary — fibre
    // drum" are different sections of the dossier, not different wording.
    summarise: (row) => `${row.role} — ${row.component} — ${row.description}`,
    fields: [
      {
        name: "role",
        label: "Packs the",
        type: "select",
        vocabulary: "packaging_role",
        required: true,
        help: "The finished product (3.2.P.7) or the drug substance as it is shipped to you (3.2.S.6). These are different sections and different qualifications — a drum is not a blister.",
      },
      {
        name: "active_ingredient_id",
        label: "Which drug substance",
        type: "select",
        vocabulary: "active_ingredient",
        help: "Only for drug-substance packaging, and only when a combination product's actives ship differently. Leave empty and the pack is filed under every substance.",
      },
      {
        name: "component",
        label: "Component",
        type: "select",
        vocabulary: "packaging_component",
        required: true,
      },
      {
        name: "description",
        label: "Description",
        type: "text",
        required: true,
        placeholder: "Aluminium foil + PVC blister",
      },
      { name: "material", label: "Material", type: "text" },
    ],
  },
  {
    id: "batch-formula",
    title: "Batch formula",
    addLabel: "Add formula line",
    blurb:
      "One line per component of the manufacturing batch. Active lines are reconciled against the declared strength and salt factor (rule R04) — this is the arithmetic a reviewer redoes by hand.",
    summarise: (row) =>
      `${row.component} — ${row.qty_per_unit_mg} mg/unit`,
    fields: [
      { name: "component", label: "Component", type: "text", required: true },
      { name: "spec", label: "Specification", type: "text", required: true, placeholder: "BP" },
      {
        name: "qty_per_unit_mg",
        label: "Quantity per unit (mg)",
        type: "number",
        required: true,
      },
      {
        name: "batch_size_units",
        label: "Batch size (units)",
        type: "number",
        required: true,
      },
      {
        name: "declared_batch_qty_kg",
        label: "Declared batch quantity (kg)",
        type: "number",
      },
      { name: "is_active", label: "This line is an active ingredient", type: "checkbox" },
      {
        name: "active_ingredient_id",
        label: "Which active",
        type: "select",
        vocabulary: "active_ingredient",
        help: "Only for an active line — it is what lets rule R04 check the salt-to-base arithmetic.",
      },
    ],
  },
  {
    id: "stability",
    title: "Stability studies",
    addLabel: "Add stability study",
    blurb:
      "The shelf life you claimed on step 1 has to be supported by a long-term study of at least that duration.",
    summarise: (row) =>
      `${row.study_type} — ${row.condition}, ${row.duration_months} months`,
    fields: [
      {
        name: "study_type",
        label: "Study type",
        type: "select",
        vocabulary: "stability_study_type",
        required: true,
      },
      {
        name: "condition",
        label: "Condition",
        type: "text",
        required: true,
        placeholder: "30 °C / 65 % RH",
      },
      {
        name: "duration_months",
        label: "Duration (months)",
        type: "number",
        required: true,
      },
      {
        name: "result_summary",
        label: "Result summary",
        type: "textarea",
        required: true,
        placeholder: "Within specification through 24 months.",
      },
    ],
  },
  {
    id: "clinical",
    title: "Clinical",
    addLabel: "Add clinical entry",
    blurb:
      "A generic filing has to show bioequivalence against the reference product (rule R06). Literature and clinical studies go here too.",
    summarise: (row) =>
      [row.kind, row.reference_product].filter(Boolean).join(" — "),
    fields: [
      {
        name: "kind",
        label: "Kind",
        type: "select",
        vocabulary: "clinical_kind",
        required: true,
      },
      {
        name: "reference_product",
        label: "Reference product",
        type: "text",
        placeholder: "Amoxil 500 mg capsules",
      },
      {
        name: "summary",
        label: "Summary",
        type: "textarea",
        required: true,
        placeholder: "Single-dose crossover study; 90% CI within 80–125%.",
      },
    ],
  },
  {
    id: "certificates",
    title: "Certificates",
    addLabel: "Add certificate",
    blurb:
      "Proof issued by someone else — a regulator, EDQM, a lab. The platform never generates these; recording one here reserves its place in the package and lets the rules tell you when it is missing or expired. A NAFDAC filing needs a CPP (rule R13).",
    summarise: (row) =>
      [row.certificate_type, row.certificate_number, row.expiry_date && `expires ${row.expiry_date}`]
        .filter(Boolean)
        .join(" — "),
    fields: [
      {
        name: "certificate_type",
        label: "Type",
        type: "select",
        vocabulary: "certificate_type",
        required: true,
      },
      { name: "issuing_authority", label: "Issuing authority", type: "text" },
      { name: "certificate_number", label: "Certificate number", type: "text" },
      { name: "issue_date", label: "Issue date", type: "date" },
      {
        name: "expiry_date",
        label: "Expiry date",
        type: "date",
        help: "Rule R13 checks the date, not just the row — an expired certificate still blocks export.",
      },
      {
        name: "manufacturer_id",
        label: "Site (GMP certificates only)",
        type: "select",
        vocabulary: "manufacturer",
        help: "A GMP certificate is site-specific; a CPP or CEP is about the product generally — leave this empty for those.",
      },
    ],
  },
];
