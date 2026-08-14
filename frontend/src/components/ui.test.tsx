import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { Badge, SeverityBadge } from "@/components/ui";
import type { Severity } from "@/lib/types";

describe("SeverityBadge", () => {
  it.each<Severity>(["ERROR", "WARNING", "INFO", "ADVISORY"])(
    "renders %s with its own styling",
    (severity) => {
      render(<SeverityBadge severity={severity} />);
      expect(screen.getByText(severity)).toBeDefined();
    },
  );

  it("gives ERROR and ADVISORY visually distinct treatments", () => {
    // A user must never mistake an AI suggestion (ADVISORY, which cannot
    // block an export) for a deterministic ERROR (which always does).
    const { container: errorBox } = render(<SeverityBadge severity="ERROR" />);
    const errorClass = errorBox.firstElementChild?.className ?? "";
    const { container: advisoryBox } = render(
      <SeverityBadge severity="ADVISORY" />,
    );
    const advisoryClass = advisoryBox.firstElementChild?.className ?? "";

    expect(errorClass).not.toBe(advisoryClass);
    expect(errorClass).toContain("red");
    expect(advisoryClass).not.toContain("red");
  });
});

describe("Badge", () => {
  it("shows export status with a matching tone", () => {
    const { container } = render(<Badge tone="bad">Blocked</Badge>);
    expect(screen.getByText("Blocked")).toBeDefined();
    expect(container.firstElementChild?.className).toContain("red");
  });
});
