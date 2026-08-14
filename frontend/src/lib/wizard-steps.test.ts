import { describe, expect, it } from "vitest";

import { CHILD_STEPS, PRODUCT_FIELDS } from "@/lib/wizard-steps";

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
