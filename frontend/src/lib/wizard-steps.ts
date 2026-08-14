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

export interface FieldSpec {
  name: string;
  label: string;
  type: "text" | "number" | "select" | "checkbox" | "textarea";
  /** Key into the vocabularies from GET /enums; required for selects. */
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
    ],
  },
  {
    id: "packaging",
    title: "Packaging",
    addLabel: "Add packaging component",
    blurb:
      "Primary, secondary and labelling components. Checked for consistency against the declared pack size (rule R12).",
    summarise: (row) => `${row.component} — ${row.description}`,
    fields: [
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
];
