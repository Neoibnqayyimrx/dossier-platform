import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ReportDownloadButton } from "@/components/ReportDownloadButton";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: { downloadValidationReport: vi.fn() },
  };
});

import { api, ApiError, attachmentFilename } from "@/lib/api";

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("ReportDownloadButton", () => {
  it("asks for this project's report", async () => {
    vi.mocked(api.downloadValidationReport).mockResolvedValueOnce(undefined);
    render(<ReportDownloadButton projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Download report (PDF)" }));

    await waitFor(() => expect(api.downloadValidationReport).toHaveBeenCalledWith("project-1"));
    expect(await screen.findByRole("button", { name: "Download report (PDF)" })).toBeDefined();
  });

  it("shows why a report could not be produced", async () => {
    vi.mocked(api.downloadValidationReport).mockRejectedValueOnce(
      new ApiError(404, "Project not found"),
    );
    render(<ReportDownloadButton projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Download report (PDF)" }));

    expect(await screen.findByText("Project not found")).toBeDefined();
  });
});

describe("attachmentFilename", () => {
  it("reads the name the server gave the file", () => {
    expect(
      attachmentFilename('attachment; filename="validation-report-examox-sequence-0000.pdf"'),
    ).toBe("validation-report-examox-sequence-0000.pdf");
  });

  it("returns null when there is nothing to read", () => {
    expect(attachmentFilename(null)).toBeNull();
    expect(attachmentFilename("inline")).toBeNull();
  });
});
