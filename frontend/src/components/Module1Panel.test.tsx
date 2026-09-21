import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { FdaApplicationCard, Module1Panel } from "@/components/Module1Panel";
import type { Applicant, Project, Vocabularies } from "@/lib/types";

// The panel talks to the API; these tests are about what it SENDS, so the
// client is replaced wholesale and each call is inspected.
vi.mock("@/lib/api", () => {
  // Same shape as the real one (status, message), so the component's
  // `instanceof ApiError` branch is the one exercised.
  class ApiError extends Error {
    blocking = [];
    constructor(
      public readonly status: number,
      message: string,
    ) {
      super(message);
    }
  }
  return {
    ApiError,
    api: {
      updateProject: vi.fn(async () => ({})),
      updateApplicant: vi.fn(async () => ({})),
      listRegionProfiles: vi.fn(async () => []),
      listApplicants: vi.fn(async () => []),
    },
  };
});

import { api, ApiError } from "@/lib/api";

const vocabularies: Vocabularies = {
  fda_application_type: [
    { value: "nda", label: "nda" },
    { value: "anda", label: "anda" },
    { value: "bla", label: "bla" },
  ],
  declaration_type: [],
};

const applicant: Applicant = {
  id: "applicant-1",
  company_name: "Exagon Pharmaceuticals Ltd",
  address: null,
  country: null,
  contact_name: "Aisha Bello",
  contact_email: "regulatory@exagon.example",
  contact_phone: "+234-800-000-0000",
  authorized_representative_name: null,
  authorized_representative_title: null,
  duns_number: null,
  created_at: "",
  updated_at: "",
};

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: "project-1",
    name: "EXAMOX ANDA",
    region: "FDA",
    product: {} as Project["product"],
    sequences: [],
    applicant,
    declarations: [],
    submission_type: "multisource-generic",
    condition_answers: {},
    application_number: null,
    fda_application_type: null,
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("FdaApplicationCard", () => {
  it("saves the application on the project and the D-U-N-S number on the applicant", async () => {
    const onChanged = vi.fn();
    render(
      <FdaApplicationCard project={project()} vocabularies={vocabularies} onChanged={onChanged} />,
    );

    fireEvent.change(screen.getByLabelText("Application type"), { target: { value: "anda" } });
    fireEvent.change(screen.getByLabelText("Application number"), {
      target: { value: "012345" },
    });
    fireEvent.change(screen.getByLabelText(/D-U-N-S number/), {
      target: { value: "999999999" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(api.updateProject).toHaveBeenCalledWith("project-1", {
      application_number: "012345",
      fda_application_type: "anda",
    });
    // One legal entity, one number for every application it files -- so it
    // is saved where that entity lives.
    expect(api.updateApplicant).toHaveBeenCalledWith("applicant-1", {
      duns_number: "999999999",
    });
  });

  it("leaves the applicant alone when its D-U-N-S number did not change", async () => {
    const onChanged = vi.fn();
    render(
      <FdaApplicationCard
        project={project({ applicant: { ...applicant, duns_number: "123456789" } })}
        vocabularies={vocabularies}
        onChanged={onChanged}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(api.updateApplicant).not.toHaveBeenCalled();
  });

  it("shows the API's refusal rather than swallowing it", async () => {
    vi.mocked(api.updateApplicant).mockRejectedValueOnce(
      new ApiError(422, "duns_number: must be exactly nine digits"),
    );
    render(
      <FdaApplicationCard project={project()} vocabularies={vocabularies} onChanged={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText(/D-U-N-S number/), { target: { value: "12-345" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/must be exactly nine digits/)).toBeDefined();
  });

  it("asks for an applicant first when there is none to hold the number", () => {
    render(
      <FdaApplicationCard
        project={project({ applicant: null })}
        vocabularies={vocabularies}
        onChanged={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText(/D-U-N-S number/)).toBeNull();
    expect(screen.getByText(/Name the applicant above first/)).toBeDefined();
  });
});

describe("Module1Panel", () => {
  it.each([
    ["FDA", true],
    ["NAFDAC", false],
    ["EU", false],
  ] as const)("shows the FDA card for a %s project: %s", async (region, shown) => {
    render(
      <Module1Panel project={project({ region })} vocabularies={vocabularies} onChanged={vi.fn()} />,
    );
    await waitFor(() => expect(api.listRegionProfiles).toHaveBeenCalled());
    expect(screen.queryByText("FDA application") !== null).toBe(shown);
  });
});

describe("Module1Panel declarations", () => {
  const profile = (region: string, slotIds: string[]) => ({
    region,
    required_certificate_types: [],
    required_declaration_types: [],
    module1_slots: slotIds.map((slot_id) => ({ slot_id, title: slot_id })),
  });

  it("says plainly when the region files no declarations at all", async () => {
    // FDA's Module 1 has no heading for a power of attorney; before this
    // note the card offered to sign documents FDA's package never carries.
    vi.mocked(api.listRegionProfiles).mockResolvedValueOnce([
      profile("FDA", ["cover-letter", "smpc", "labelling"]),
    ] as never);
    render(<Module1Panel project={project()} vocabularies={vocabularies} onChanged={vi.fn()} />);
    expect(await screen.findByText(/has no place for these declarations/)).toBeDefined();
    expect(screen.queryByText(/not modelled yet/)).toBeNull();
  });

  it("keeps the not-modelled caution for a region that does file them", async () => {
    vi.mocked(api.listRegionProfiles).mockResolvedValueOnce([
      profile("EU", ["cover-letter", "declarations"]),
    ] as never);
    render(
      <Module1Panel
        project={project({ region: "EU" })}
        vocabularies={vocabularies}
        onChanged={vi.fn()}
      />,
    );
    expect(await screen.findByText(/not modelled yet/)).toBeDefined();
    expect(screen.queryByText(/has no place for these declarations/)).toBeNull();
  });
});
