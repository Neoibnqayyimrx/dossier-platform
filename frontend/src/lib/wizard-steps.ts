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
  /**
   * The resource this step edits.
   *
   * Every step but one names a factory-backed child collection, which is
   * what lets the generic form POST and DELETE against it. P23's product
   * information is the exception and is typed as the exception rather
   * than smuggled into `ProductChildResource`: it is a 1:1 resource with
   * a PUT and no collection verbs, so widening that union would make
   * `api.createProductChild(id, "product-information", ...)` typecheck
   * against an endpoint that does not exist. It reaches this field only
   * because it has a `customEditor`, and the generic path is never taken
   * for it.
   */
  id: ProductChildResource | "product-information";
  title: string;
  /**
   * The add-button label, written out rather than derived from `title`.
   * A `.replace(/s$/, "")` singulariser looks fine until "Stability
   * studies" becomes "Add stability studie" -- English plurals are not
   * regex-able, so the singular is data like everything else here.
   */
  addLabel: string;
  blurb: string;
  /**
   * Collections that must already have a row before this step can be
   * FILLED IN. Looking at it is never gated -- see `lockForStep`.
   *
   * Deliberately hand-written and deliberately short. The tempting
   * version derives it: four field specs point at a runtime vocabulary
   * (a select fed by rows you saved earlier), so a step could be said to
   * require whatever feeds those. Three of those four are OPTIONAL fields
   * whose own help text says to leave them empty -- packaging's drug
   * substance, batch-formula's active, a certificate's site -- and
   * locking a step over a dropdown the filer is entitled to ignore would
   * be inventing a rule no regulator asked for. Only the fourth is real:
   * rule R17 says the backbone cannot name a drug substance without its
   * manufacturer, so an active ingredient genuinely cannot be entered
   * before a site exists.
   */
  requires?: readonly ProductChildResource[];
  /** How one saved row is summarised in the list. Absent for a step with
   * a `customEditor`, which renders no such list -- a summariser nothing
   * calls is a summariser that quietly goes stale. */
  summarise?: (row: Record<string, unknown>) => string;
  fields: FieldSpec[];
  /**
   * P21: this step is NOT the generic add-a-row form.
   *
   * Everything else in this file is a list of field specs, and that shape
   * has paid off five times over -- adding a field is a one-line edit and
   * six collections share one component. Stability is the one place it
   * stops working, and the reason is arithmetic: a real study is five
   * timepoints across eight tests, and forty trips round an "add row" form
   * is unusable. The two questions such a form would have to ask on every
   * value -- which test, which timepoint -- are exactly the two a grid
   * answers by POSITION.
   *
   * This flag exists so that this file stays a complete answer to "what
   * does the wizard ask for". Before it, the field specs WERE the whole
   * wizard; now they are the wizard with a footnote, and the footnote has
   * to be visible where the next person adding a field will look.
   *
   * See src/components/StabilityGrid.tsx for the full cost of the
   * deviation. It is worth making exactly once, here, because the shape of
   * the DATA is a table -- it is not a licence to hand-write the next
   * screen.
   */
  customEditor?: "drug-product-control" | "bioequivalence" | "product-information";
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
  // P22. The comparator the APPLICATION claims equivalence to. It is a
  // field on the PRODUCT and not on the study for the same reason the
  // shelf life is a field on the product and not on the stability data:
  // it is the claim, the study is the evidence, and rule R26 reconciles
  // them. Collapsing the two would make that check a comparison of a
  // value with itself.
  {
    name: "reference_product_name",
    label: "Reference product (comparator)",
    type: "text",
    placeholder: "Amoxil 500 mg capsules",
    help: "Printed on the registration form (1.2.2) and the QOS (2.3). Rule R26 checks it against the comparator your study actually dosed.",
  },
  {
    name: "reference_product_manufacturer",
    label: "Reference product manufacturer",
    type: "text",
    help: "A generic is equivalent to a specific innovator product, not to a name.",
  },
  {
    name: "narrow_therapeutic_index",
    label: "Narrow therapeutic index drug",
    type: "checkbox",
    help: "Warfarin, digoxin, levothyroxine, lithium, phenytoin. Tightens the bioequivalence acceptance window from 80.00-125.00 % to 90.00-111.11 % (rule R25).",
  },
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
    // R17: an active ingredient names the site that makes it, and the
    // dropdown that names it is built from the previous step's rows.
    requires: ["manufacturers"],
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
    title: "Drug product control and stability",
    addLabel: "Add stability study",
    blurb:
      "The finished product's specification (3.2.P.5.1), the batches measured against it (3.2.P.5.4), and the stability studies that justify the shelf life you claimed on step 1 (3.2.P.8). Enter the stability results as a table — paste one straight from your spreadsheet.",
    // A grid, not a form -- see `customEditor` above. The field specs are
    // empty rather than describing a form nobody renders: a spec list that
    // does not drive anything is a list that quietly goes stale.
    customEditor: "drug-product-control",
    fields: [],
  },
  {
    id: "bioequivalence",
    title: "Bioequivalence",
    addLabel: "Add bioequivalence study",
    blurb:
      "For a generic, this is the document the approval turns on: 5.3.1.2 carries the entire scientific argument. Enter the comparator, the study and its three confidence intervals here, and the BTI form (1.4.1) and the tabular listing (5.2) are generated from them - nothing is retyped onto either.",
    // A comparator that other rows point at, and a fixed three-row results
    // table. Neither fits the generic add-a-row form -- see
    // `customEditor` above and BioequivalenceEditor.tsx for the full
    // reasoning. This is the second deviation, not a new licence: both
    // exist because the shape of the DATA is not a list.
    customEditor: "bioequivalence",
    fields: [],
  },
  {
    id: "product-information",
    title: "Product information",
    addLabel: "Add product information",
    blurb:
      "The SmPC (1.3.1), the outer and inner labels (1.3.2) and the patient leaflet (1.3.3) — all three rendered from one dataset. Type the clinical particulars here; the strength, shelf life, storage, pack and ingredient list are read from what you have already entered, so the three documents cannot end up disagreeing.",
    // The third custom editor, and the first that is not about tabular
    // data. Half of this screen is deliberately NOT editable -- see
    // ProductInformationEditor.tsx. A field spec describes an input, and
    // there is no honest way to spell "this is section 6.3, it says 24
    // months, and it is not yours to type" as one.
    customEditor: "product-information",
    fields: [],
  },
  {
    id: "clinical",
    title: "Clinical",
    addLabel: "Add clinical entry",
    blurb:
      "Literature references (5.4) and any other clinical study. The bioequivalence study is NOT here any more - it is structured data on the previous step, because a paragraph cannot carry a confidence interval and 1.4.1 is generated entirely from those.",
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

/**
 * The product form, one step per child collection, then the review.
 * Exported so the wizard and the stepper cannot disagree about how many
 * circles to draw.
 */
export const TOTAL_STEPS = 1 + CHILD_STEPS.length + 1;

/** Where a collection's step sits, so a lock can offer to take you there. */
export function stepIndexOfResource(resource: ProductChildResource): number {
  return CHILD_STEPS.findIndex((step) => step.id === resource) + 1;
}

/** The human name of any step, including the two that are not children. */
export function titleOfStep(index: number): string {
  if (index === 0) return "Product";
  if (index === TOTAL_STEPS - 1) return "Create the project";
  return CHILD_STEPS[index - 1]?.title ?? "";
}

/** The lock every step but the first wears until the product exists. */
export const PRODUCT_FIRST: StepLock = {
  reason:
    "Save the product on step 1 first. Every later step attaches its rows to that product, so there is nowhere to put them until it exists.",
  goToStep: 0,
};

export interface StepLock {
  /** What has to happen first, written for the filer, not the developer. */
  reason: string;
  /** The step that fixes it. */
  goToStep: number;
}

/**
 * Whether step `index` can be filled in, and if not, why.
 *
 * WHY this is a pure function in this file rather than a condition inside
 * the wizard component: it is the rule, and a rule you can call with three
 * plain arguments is a rule you can test without rendering anything. The
 * wizard decides what a lock LOOKS like; this decides whether there is one.
 *
 * Note what it deliberately does NOT do: require every step in order. Most
 * of these collections are legitimately empty in a real filing -- a
 * generic with a biowaiver files no bioequivalence study, a filing with no
 * literature files no clinical entry -- so a strict "finish step N before
 * step N+1" chain would block dossiers that are correct as they stand.
 * What is genuinely required is decided later, per region and submission
 * type, by the validation rules the project runs (P06/P17), which can see
 * the whole filing. This gate only enforces what is structurally
 * impossible: attaching a row to a product that does not exist yet, and
 * the one cross-reference R17 makes mandatory.
 */
export function lockForStep(
  index: number,
  productSaved: boolean,
  rows: Readonly<Record<string, readonly unknown[]>>,
): StepLock | null {
  // Step 1 is where the product is created, so it can never be waiting on it.
  if (index === 0) return null;

  if (!productSaved) return PRODUCT_FIRST;

  const step = CHILD_STEPS[index - 1];
  // The review step: past the children, and gated only on the product.
  if (step === undefined) return null;

  for (const resource of step.requires ?? []) {
    if ((rows[resource] ?? []).length === 0) {
      const blocking = stepIndexOfResource(resource);
      return {
        reason: `Add at least one entry on step ${blocking + 1} (${titleOfStep(blocking)}) first — this step points at it.`,
        goToStep: blocking,
      };
    }
  }

  return null;
}
