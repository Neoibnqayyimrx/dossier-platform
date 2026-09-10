import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import NewProductPage from "@/app/products/new/page";
import { AuthProvider } from "@/lib/auth";
import { storeToken } from "@/lib/api";
import { TOTAL_STEPS, titleOfStep } from "@/lib/wizard-steps";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }),
}));

// The wizard's own two GETs on mount: the controlled vocabularies every
// dropdown is built from, and the applicants offered on the last step.
function mockBackend() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () =>
        String(url).includes("/enums") ? { region: [] } : [],
    })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("moving around the wizard before it is filled in", () => {
  it("lets you open any of the twelve stages without finishing the first", async () => {
    // The whole point of the feature: a filer being asked for a dossier's
    // worth of data can look at what is coming before committing to it.
    storeToken("t");
    mockBackend();
    render(
      <AuthProvider>
        <NewProductPage />
      </AuthProvider>,
    );
    await screen.findByRole("button", { name: "Save and continue" });

    // Step 7 is deep in the middle, and nothing has been saved.
    fireEvent.click(screen.getByTitle(`7. ${titleOfStep(6)} — preview only`));

    expect(await screen.findByText(/Preview only/)).toBeDefined();
    expect(screen.getByRole("heading", { name: titleOfStep(6) })).toBeDefined();
  });

  it("renders that preview read-only", async () => {
    storeToken("t");
    mockBackend();
    render(
      <AuthProvider>
        <NewProductPage />
      </AuthProvider>,
    );
    await screen.findByRole("button", { name: "Save and continue" });
    fireEvent.click(screen.getByTitle(`2. ${titleOfStep(1)} — preview only`));

    // A <fieldset disabled> disables every control inside it, which is
    // what makes "you can look but not type" true rather than decorative.
    //
    // Asserted with :disabled rather than the `disabled` PROPERTY, which
    // reflects only a control's own attribute and answers false for one
    // disabled by an ancestor fieldset. The pseudo-class is the question
    // actually being asked: can the user interact with this?
    await waitFor(() => expect(screen.getByText(/Preview only/)).toBeDefined());

    expect(
      screen.getByRole("button", { name: /Add manufactur/i }).matches(":disabled"),
    ).toBe(true);
    // The fields themselves, not just the submit button.
    for (const box of screen.getAllByRole("textbox")) {
      expect(box.matches(":disabled")).toBe(true);
    }
  });

  it("marks every stage but the first as locked while nothing is saved", async () => {
    storeToken("t");
    mockBackend();

    render(
      <AuthProvider>
        <NewProductPage />
      </AuthProvider>,
    );
    await screen.findByRole("button", { name: "Save and continue" });

    for (let index = 1; index < TOTAL_STEPS; index += 1) {
      expect(
        screen.getByTitle(`${index + 1}. ${titleOfStep(index)} — preview only`),
      ).toBeDefined();
    }
    // Step 1 is where the product is created, so it is never locked.
    expect(screen.getByTitle(`1. ${titleOfStep(0)}`)).toBeDefined();
  });
});
