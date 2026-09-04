import { describe, expect, it } from "vitest";

import { CHILD_STEPS, PRODUCT_FIELDS, RUNTIME_VOCABULARIES } from "@/lib/wizard-steps";

describe("wizard step specs", () => {
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
    for (const step of CHILD_STEPS) {
      const required = Object.fromEntries(
        step.fields
          .filter((f) => f.required)
          .map((f) => [f.name, f.type === "number" ? 1 : "x"]),
      );
      expect(step.summarise(required)).not.toContain("undefined");
    }
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

    expect(runtimeFields.map((f) => f.name).sort()).toEqual([
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
