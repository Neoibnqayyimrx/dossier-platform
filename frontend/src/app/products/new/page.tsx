"use client";

/**
 * The Product Information Wizard.
 *
 * This screen is the product's whole thesis: it captures structured DATA
 * and never asks anyone to upload a finished dossier. Every field here is
 * something a regulator later cross-checks across modules, which is why it
 * is typed, vocabulary-constrained, and stored once (AGENTS.md §5's
 * determinism boundary) rather than retyped into prose.
 *
 * WHY it saves as you go rather than collecting everything and POSTing at
 * the end: step 1 creates the Product and every later step attaches
 * children to that id, exactly as the API is shaped. A half-finished
 * product is a legitimate state -- the completeness rules (P06) are what
 * decide whether it can be exported, not the form.
 */

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api, ApiError, type ProductChildResource } from "@/lib/api";
import type { Vocabularies } from "@/lib/types";
import { SpecificationEditor } from "@/components/SpecificationEditor";
import { CHILD_STEPS, PRODUCT_FIELDS, type ChildStepSpec } from "@/lib/wizard-steps";
import { AuthGuard } from "@/components/AuthGuard";
import { Field } from "@/components/Field";
import { Card, ErrorNotice, PageHeading } from "@/components/ui";

type Draft = Record<string, unknown>;
type SavedRows = Record<string, Draft[]>;

const buttonClass =
  "rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900";
const secondaryButtonClass =
  "rounded-md border border-slate-300 px-4 py-2 text-sm font-medium disabled:opacity-50 dark:border-slate-700";

function Stepper({ current, total }: { current: number; total: number }) {
  return (
    <ol className="mb-6 flex flex-wrap gap-2 text-xs">
      {Array.from({ length: total }, (_, index) => (
        <li
          key={index}
          className={`rounded-full px-2.5 py-1 ${
            index === current
              ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
              : index < current
                ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
          }`}
        >
          {index + 1}
        </li>
      ))}
    </ol>
  );
}

function ChildStep({
  step,
  productId,
  vocabularies,
  rows,
  onSaved,
  onDeleted,
}: {
  step: ChildStepSpec;
  productId: string;
  vocabularies: Vocabularies;
  rows: Draft[];
  onSaved: (resource: ProductChildResource, row: Draft) => void;
  onDeleted: (resource: ProductChildResource, id: string) => void;
}) {
  const [draft, setDraft] = useState<Draft>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const update = useCallback(
    (name: string, value: unknown) =>
      setDraft((previous) => ({ ...previous, [name]: value })),
    [],
  );

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const saved = await api.createProductChild(productId, step.id, draft);
      onSaved(step.id, { ...draft, ...saved });
      setDraft({});
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    try {
      await api.deleteProductChild(productId, step.id, id);
      onDeleted(step.id, id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete");
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600 dark:text-slate-400">{step.blurb}</p>

      {rows.length > 0 && (
        <ul className="space-y-2">
          {rows.map((row) => (
            <li
              key={String(row.id)}
              className="rounded-md border border-slate-200 px-3 py-2 text-sm dark:border-slate-800"
            >
              <div className="flex items-center justify-between">
                <span>{step.summarise(row)}</span>
                <button
                  type="button"
                  onClick={() => remove(String(row.id))}
                  className="text-xs text-slate-500 hover:text-red-600"
                >
                  Remove
                </button>
              </div>
              {/* Each active ingredient carries its own 3.2.S.4.1
                  specification -- the section repeats per drug substance,
                  so the table belongs to the substance, not the product. */}
              {step.id === "apis" && (
                <SpecificationEditor
                  apiId={String(row.id)}
                  substanceName={String(row.inn_name ?? "this substance")}
                />
              )}
            </li>
          ))}
        </ul>
      )}

      <Card>
        <form onSubmit={add} className="space-y-3">
          {error && <ErrorNotice message={error} />}
          <div className="grid gap-3 sm:grid-cols-2">
            {step.fields.map((spec) => (
              <div
                key={spec.name}
                className={spec.type === "textarea" ? "sm:col-span-2" : ""}
              >
                <Field
                  spec={spec}
                  value={draft[spec.name]}
                  vocabularies={vocabularies}
                  onChange={update}
                />
              </div>
            ))}
          </div>
          <button type="submit" disabled={busy} className={secondaryButtonClass}>
            {busy ? "Adding…" : step.addLabel}
          </button>
        </form>
      </Card>
    </div>
  );
}

function Wizard() {
  const router = useRouter();
  const [vocabularies, setVocabularies] = useState<Vocabularies | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [productId, setProductId] = useState<string | null>(null);
  const [productDraft, setProductDraft] = useState<Draft>({});
  const [rows, setRows] = useState<SavedRows>({});
  const [projectDraft, setProjectDraft] = useState<Draft>({ region: "NAFDAC" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .getEnums()
      .then(setVocabularies)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Could not load vocabularies"),
      );
  }, []);

  const totalSteps = 1 + CHILD_STEPS.length + 1; // product + children + review

  const updateProduct = useCallback(
    (name: string, value: unknown) =>
      setProductDraft((previous) => ({ ...previous, [name]: value })),
    [],
  );

  const handleSaved = useCallback(
    (resource: ProductChildResource, row: Draft) =>
      setRows((previous) => ({
        ...previous,
        [resource]: [...(previous[resource] ?? []), row],
      })),
    [],
  );

  const handleDeleted = useCallback(
    (resource: ProductChildResource, id: string) =>
      setRows((previous) => ({
        ...previous,
        [resource]: (previous[resource] ?? []).filter(
          (row) => String(row.id) !== id,
        ),
      })),
    [],
  );

  async function saveProduct(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      // Idempotent forward navigation: re-entering step 1 after going
      // back must not create a second Product.
      if (productId === null) {
        const product = await api.createProduct(productDraft);
        setProductId(product.id);
      }
      setStepIndex(1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the product");
    } finally {
      setBusy(false);
    }
  }

  async function createProject(event: React.FormEvent) {
    event.preventDefault();
    if (!productId) return;
    setError(null);
    setBusy(true);
    try {
      const project = await api.createProject({
        name: String(projectDraft.name ?? ""),
        region: String(projectDraft.region ?? "NAFDAC"),
        product_id: productId,
      });
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the project");
    } finally {
      setBusy(false);
    }
  }

  if (error && vocabularies === null) return <ErrorNotice message={error} />;
  if (vocabularies === null)
    return <p className="text-sm text-slate-500">Loading…</p>;

  const isProductStep = stepIndex === 0;
  const isReviewStep = stepIndex === totalSteps - 1;
  const childStep = !isProductStep && !isReviewStep ? CHILD_STEPS[stepIndex - 1] : null;

  return (
    <>
      <PageHeading
        title="New product"
        subtitle="Capture the data. The dossier is generated from it — you never upload one."
      />
      <Stepper current={stepIndex} total={totalSteps} />

      {isProductStep && (
        <Card>
          <form onSubmit={saveProduct} className="space-y-4">
            {error && <ErrorNotice message={error} />}
            <div className="grid gap-3 sm:grid-cols-2">
              {PRODUCT_FIELDS.map((spec) => (
                <Field
                  key={spec.name}
                  spec={spec}
                  value={productDraft[spec.name]}
                  vocabularies={vocabularies}
                  onChange={updateProduct}
                />
              ))}
            </div>
            <button type="submit" disabled={busy} className={buttonClass}>
              {busy ? "Saving…" : productId ? "Continue" : "Save and continue"}
            </button>
          </form>
        </Card>
      )}

      {childStep && productId && (
        <>
          <h2 className="mb-3 text-lg font-medium">{childStep.title}</h2>
          <ChildStep
            step={childStep}
            productId={productId}
            vocabularies={vocabularies}
            rows={rows[childStep.id] ?? []}
            onSaved={handleSaved}
            onDeleted={handleDeleted}
          />
        </>
      )}

      {isReviewStep && (
        <Card>
          <h2 className="mb-1 text-lg font-medium">Create the project</h2>
          <p className="mb-4 text-sm text-slate-600 dark:text-slate-400">
            A project files this product to one regulator. The region decides
            which Module 1 documents and which builders apply.
          </p>
          <form onSubmit={createProject} className="space-y-4">
            {error && <ErrorNotice message={error} />}
            <Field
              spec={{ name: "name", label: "Project name", type: "text", required: true }}
              value={projectDraft.name}
              vocabularies={vocabularies}
              onChange={(name, value) =>
                setProjectDraft((previous) => ({ ...previous, [name]: value }))
              }
            />
            <Field
              spec={{
                name: "region",
                label: "Region",
                type: "select",
                vocabulary: "region",
                required: true,
              }}
              value={projectDraft.region}
              vocabularies={vocabularies}
              onChange={(name, value) =>
                setProjectDraft((previous) => ({ ...previous, [name]: value }))
              }
            />
            <button type="submit" disabled={busy} className={buttonClass}>
              {busy ? "Creating…" : "Create project"}
            </button>
          </form>
        </Card>
      )}

      {!isProductStep && (
        <div className="mt-6 flex items-center justify-between">
          <button
            type="button"
            onClick={() => setStepIndex((index) => index - 1)}
            className={secondaryButtonClass}
          >
            Back
          </button>
          {!isReviewStep && (
            <button
              type="button"
              onClick={() => setStepIndex((index) => index + 1)}
              className={buttonClass}
            >
              Next
            </button>
          )}
        </div>
      )}
    </>
  );
}

export default function NewProductPage() {
  return (
    <AuthGuard>
      <Wizard />
    </AuthGuard>
  );
}
