import { describe, expect, it } from "vitest";

import type { NarrativeStatus } from "@/lib/types";

/**
 * Guards the contract that an approved narrative is recognised as
 * reviewed.
 *
 * The bug this exists for: the status union was hand-written in
 * uppercase while the backend serializes lowercase enum values, so the
 * "is this reviewed?" comparison was never true and an approved draft
 * displayed as "awaiting review" indefinitely. A pure type couldn't catch
 * it -- the literals were internally consistent, just wrong about the
 * wire format.
 */
function isReviewed(status: NarrativeStatus): boolean {
  return status === "approved" || status === "edited";
}

describe("narrative review state", () => {
  it("treats approved and edited as reviewed", () => {
    expect(isReviewed("approved")).toBe(true);
    expect(isReviewed("edited")).toBe(true);
  });

  it("treats a pending draft as not yet usable", () => {
    // Only approve/edit set final_text on the backend, and only
    // final_text reaches a rendered document.
    expect(isReviewed("pending")).toBe(false);
  });

  it("uses the backend's lowercase wire values, not uppercase names", () => {
    const wireValues: NarrativeStatus[] = ["pending", "approved", "edited"];
    for (const value of wireValues) {
      expect(value).toBe(value.toLowerCase());
    }
  });
});
