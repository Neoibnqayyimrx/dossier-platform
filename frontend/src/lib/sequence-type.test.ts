import { describe, expect, it } from "vitest";

import { defaultSubmissionUnitType } from "@/lib/sequence-type";

describe("defaultSubmissionUnitType", () => {
  it("files a project's first sequence as the application itself", () => {
    expect(defaultSubmissionUnitType(0)).toBe("initial");
  });

  it("files every later sequence as a response, which FDA requires", () => {
    // FDA allows one "application" per regulatory activity; a second
    // `initial` is refused by the builder (app/ectd/us_regional.py).
    expect(defaultSubmissionUnitType(1)).toBe("response");
    expect(defaultSubmissionUnitType(7)).toBe("response");
  });
});
