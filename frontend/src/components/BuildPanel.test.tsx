import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { BuildPanel } from "@/components/BuildPanel";
import type { Sequence, Vocabularies } from "@/lib/types";

vi.mock("@/lib/api", () => {
  class ApiError extends Error {
    constructor(
      public readonly status: number,
      message: string,
      public readonly blocking: unknown[] = [],
    ) {
      super(message);
    }
  }
  return {
    ApiError,
    api: {
      createSequence: vi.fn(),
      updateSequence: vi.fn(),
      buildEctd: vi.fn(),
      buildCtd: vi.fn(),
      downloadArtifact: vi.fn(),
    },
  };
});

import { api, ApiError } from "@/lib/api";

const vocabularies: Vocabularies = {
  submission_unit_type: [
    { value: "initial", label: "initial" },
    { value: "response", label: "response" },
  ],
};

function sequence(id: string, number: string, submission_unit_type: string): Sequence {
  return {
    id,
    project_id: "project-1",
    number,
    description: null,
    submitted_at: null,
    submission_unit_type,
    created_at: "",
    updated_at: "",
  };
}

const built = (number: string) => ({ storage_key: `k/${number}.zip`, sequence_number: number, operations: {}, overrides: [] });

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

function renderPanel(sequenceCount = 0) {
  render(
    <BuildPanel
      projectId="project-1"
      region="FDA"
      sequenceCount={sequenceCount}
      vocabularies={vocabularies}
    />,
  );
  return {
    select: () => screen.getByLabelText("The next sequence is") as HTMLSelectElement,
    build: () => fireEvent.click(screen.getByRole("button", { name: "Build next eCTD sequence" })),
  };
}

describe("BuildPanel", () => {
  it("files a project's first sequence as initial and the next as a response", async () => {
    vi.mocked(api.createSequence).mockResolvedValueOnce(sequence("s1", "0001", "initial"));
    vi.mocked(api.buildEctd).mockResolvedValueOnce(built("0001"));
    const panel = renderPanel(0);

    expect(panel.select().value).toBe("initial");
    panel.build();

    await screen.findByRole("button", { name: "Download sequence 0001" });
    expect(api.createSequence).toHaveBeenCalledWith("project-1", {
      submission_unit_type: "initial",
    });
    expect(panel.select().value).toBe("response");
  });

  it("retries the SAME sequence after a refused build instead of burning a number", async () => {
    // The trap this guards: a refused build left sequence 0001 on file, so
    // the retry created 0002 as `initial` -- which FDA refuses, 0001 being
    // the "original application" -- and the only way out was to file the
    // real application as an amendment to something FDA never received.
    vi.mocked(api.createSequence).mockResolvedValueOnce(sequence("s1", "0001", "initial"));
    vi.mocked(api.buildEctd)
      .mockRejectedValueOnce(new ApiError(422, "Cannot build FDA's Module 1 backbone without the FDA application number (rule R34)."))
      .mockResolvedValueOnce(built("0001"));
    const panel = renderPanel(0);

    panel.build();
    expect(await screen.findByText(/without the FDA application number/)).toBeDefined();
    expect(panel.select().value).toBe("initial"); // still the first sequence

    panel.build();
    await screen.findByRole("button", { name: "Download sequence 0001" });
    expect(api.createSequence).toHaveBeenCalledTimes(1);
    expect(vi.mocked(api.buildEctd).mock.calls.map((call) => call[1])).toEqual(["s1", "s1"]);
  });

  it("restates the retried sequence's type if the filer changed it in between", async () => {
    vi.mocked(api.createSequence).mockResolvedValueOnce(sequence("s2", "0002", "initial"));
    vi.mocked(api.updateSequence).mockResolvedValueOnce(sequence("s2", "0002", "response"));
    vi.mocked(api.buildEctd)
      .mockRejectedValueOnce(new ApiError(422, "Sequence 0002 is marked 'initial'"))
      .mockResolvedValueOnce(built("0002"));
    // Forced to `initial` below to reproduce a filer overriding the default.
    const panel = renderPanel(1);
    fireEvent.change(panel.select(), { target: { value: "initial" } });

    panel.build();
    await screen.findByText(/marked 'initial'/);
    fireEvent.change(panel.select(), { target: { value: "response" } });
    panel.build();

    await waitFor(() => expect(api.updateSequence).toHaveBeenCalledWith("project-1", "s2", {
      submission_unit_type: "response",
    }));
    await screen.findByRole("button", { name: "Download sequence 0002" });
    expect(api.createSequence).toHaveBeenCalledTimes(1);
  });
});
