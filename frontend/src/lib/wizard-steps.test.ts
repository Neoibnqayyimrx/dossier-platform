import { describe, expect, it } from "vitest";

import { CHILD_STEPS, PRODUCT_FIELDS, RUNTIME_VOCABULARIES } from "@/lib/wizard-steps";

describe("wizard step specs", () => {
  it("gives every step with a row list an editor of some kind", () => {
    // The one deviation from the generic shape is deliberate and is
    // declared, not inferred: a step either has field specs to render a
    // form from, or names a custom editor. Neither would be a step that
    // renders nothing.
    for (const step of CHILD_STEPS) {
      expect(
        step.fields.length > 0 || step.customEditor !== undefined,
        `${step.title} has no fields and no customEditor`,
      ).toBe(true);
    }
  });

  it("gives every child step a hand-written add label", () => {
    // Regression: deriving the singular with `.replace(/s$/, "")` turned
    // "Stability studies" into "Add stability studie". English plurals
    // are not regex-able.
    for (const step of CHILD_STEPS) {
      expect(step.addLabel, `${step.title} has no addLabel`).toBeTruthy();
      expect(step.addLabel).not.toMatch(/studie$/);
      expect(step.addLabel.startsWith("Add ")).toBe(true);
    }
  });

  it("names a vocabulary for every select, so no option list is hard-coded", () => {
    const allFields = [
      ...PRODUCT_FIELDS,
      ...CHILD_STEPS.flatMap((step) => step.fields),
    ];
    for (const field of allFields) {
      if (field.type === "select") {
        expect(field.vocabulary, `${field.name} is a select with no vocabulary`).toBeTruthy();
      }
    }
  });

  it("summarises a row without leaking 'undefined' when optional fields are blank", () => {
    // A step with a `customEditor` renders no row list and therefore has
    // no summariser -- see ChildStepSpec.customEditor for why two steps
    // are allowed to leave the generic shape, and why that is a bounded
    // exception rather than a new pattern.
    for (const step of CHILD_STEPS.filter((s) => s.summarise)) {
      const required = Object.fromEntries(
        step.fields
          .filter((f) => f.required)
          .map((f) => [f.name, f.type === "number" ? 1 : "x"]),
      );
      expect(step.summarise!(required)).not.toContain("undefined");
    }
  });
});

describe("the custom editors stay a bounded exception", () => {
  it("keeps hand-written editors to the three steps that have earned one", () => {
    // A guard rather than a preference. The generic form is what makes
    // "add a field" a one-line edit, and each hand-written editor is a
    // screen that has to be maintained by hand forever. Each one has to
    // argue for itself by failing this test first.
    //
    // Two are justified by their data being a TABLE: stability is a
    // timepoint x test grid, and bioequivalence is a fixed three-parameter
    // results table pointing at a comparator row that other rows reference.
    //
    // P23's product information is the third, and its argument is
    // different -- which is why it had to fail this test to get in rather
    // than being waved through as "one more editor". Half of that screen
    // is NOT EDITABLE: sections 1, 2, 3, 6.1, 6.3, 6.4 and 6.5 of the SmPC
    // are derived from the product, its packaging and its stability data,
    // and shown read-only with a sentence saying where each comes from. A
    // FieldSpec describes an input; there is no honest way to spell "this
    // is section 6.3, it says 24 months, and it is not yours to type" as
    // one. See ProductInformationEditor.tsx.
    const custom = CHILD_STEPS.filter((step) => step.customEditor).map((step) => step.id);
    expect(custom.sort()).toEqual([
      "bioequivalence",
      "product-information",
      "stability",
    ]);
  });
});

describe("cross-reference fields", () => {
  it("only points at vocabularies the wizard builds at runtime", () => {
    // These two selects are filled from rows saved in an EARLIER step, not
    // from /enums. A typo here is a dropdown that silently offers nothing
    // -- and R17 (an active with no manufacturer) then blocks the export
    // with no way for the user to see why.
    const runtimeFields = CHILD_STEPS.flatMap((step) =>
      step.fields.filter((field) =>
        (RUNTIME_VOCABULARIES as readonly string[]).includes(field.vocabulary ?? ""),
      ),
    );

    // Two `active_ingredient_id` selects since P19: the batch-formula
    // line's (which active is this line?) and the packaging row's (which
    // substance does this drum hold?). Both are cross-references to rows
    // saved in an earlier step, which is exactly what a runtime vocabulary
    // is for.
    expect(runtimeFields.map((f) => f.name).sort()).toEqual([
      "active_ingredient_id",
      "active_ingredient_id",
      "manufacturer_id",
      "manufacturer_id",
    ]);
    for (const field of runtimeFields) {
      expect(field.type).toBe("select");
    }
  });

  it("captures every collection the rules need before a NAFDAC export", () => {
    // The audit that opened P15 found four collections with endpoints and
    // no way in: clinical (R06), batch formula (R04), certificates (R13)
    // and the API-to-manufacturer link (R17).
    const ids = CHILD_STEPS.map((step) => step.id);
    expect(ids).toContain("clinical");
    expect(ids).toContain("batch-formula");
    expect(ids).toContain("certificates");
  });
});
