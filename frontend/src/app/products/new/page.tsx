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

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { api, ApiError, type ProductChildResource } from "@/lib/api";
import type {
  Applicant,
  BatchAnalysis,
  SpecificationTest,
  Vocabularies,
} from "@/lib/types";
import { BatchAnalysisEditor } from "@/components/BatchAnalysisEditor";
import { SpecificationEditor } from "@/components/SpecificationEditor";
import { BioequivalenceEditor } from "@/components/BioequivalenceEditor";
import { ProductInformationEditor } from "@/components/ProductInformationEditor";
import { StabilityGrid } from "@/components/StabilityGrid";
import {
  CHILD_STEPS,
  PRODUCT_FIELDS,
  PRODUCT_FIRST,
  TOTAL_STEPS,
  lockForStep,
  titleOfStep,
  type ChildStepSpec,
  type RuntimeVocabulary,
  type StepLock,
} from "@/lib/wizard-steps";
import type { EnumOption } from "@/lib/types";
import { AuthGuard } from "@/components/AuthGuard";
import { Field } from "@/components/Field";
import { Card, ErrorNotice, PageHeading } from "@/components/ui";

type Draft = Record<string, unknown>;
type SavedRows = Record<string, Draft[]>;

const buttonClass =
  "rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900";
const secondaryButtonClass =
  "rounded-md border border-slate-300 px-4 py-2 text-sm font-medium disabled:opacity-50 dark:border-slate-700";

/** The applicant form shown at the last step when you are not reusing one
 * you already have. Kept here rather than in wizard-steps.ts because an
 * Applicant is not a product child -- it is master data of its own. */
const APPLICANT_FIELDS = [
  { name: "company_name", label: "Company name", type: "text" as const, required: true },
  { name: "country", label: "Country", type: "text" as const },
  { name: "address", label: "Address", type: "text" as const },
  { name: "contact_name", label: "Contact name", type: "text" as const },
  { name: "contact_email", label: "Contact email", type: "text" as const },
  {
    name: "authorized_representative_name",
    label: "Authorised representative",
    type: "text" as const,
    help: "The named signatory — for a foreign manufacturer filing through a Nigerian agent, usually the agent's regulatory lead.",
  },
  {
    name: "authorized_representative_title",
    label: "Representative title",
    type: "text" as const,
  },
];

/** A preview's controls are disabled, so nothing can call this. */
const NO_OP = () => {};

/**
 * The twelve circles, and the only way to move between steps other than
 * Back/Next.
 *
 * WHY a locked step is still clickable: the filer is being asked for a
 * dossier's worth of data across twelve screens, and "what am I going to
 * be asked for?" is a fair question to want answered before starting. The
 * lock is on TYPING, not on LOOKING -- so every circle navigates, and a
 * step you have not earned yet opens read-only instead of refusing.
 */
function Stepper({
  current,
  total,
  lockAt,
  onJump,
}: {
  current: number;
  total: number;
  lockAt: (index: number) => StepLock | null;
  onJump: (index: number) => void;
}) {
  return (
    <ol className="mb-6 flex flex-wrap gap-2 text-xs">
      {Array.from({ length: total }, (_, index) => {
        const locked = lockAt(index) !== null;
        const isCurrent = index === current;
        return (
          <li key={index}>
            <button
              type="button"
              onClick={() => onJump(index)}
              // Screen readers get the step's name and its state, and
              // sighted users get the same on hover. A bare number is not
              // a label anyone can act on.
              aria-current={isCurrent ? "step" : undefined}
              title={`${index + 1}. ${titleOfStep(index)}${
                locked ? " — preview only" : ""
              }`}
              className={`rounded-full px-2.5 py-1 transition-colors ${
                isCurrent
                  ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                  : locked
                    ? "border border-dashed border-slate-300 text-slate-400 hover:border-slate-400 hover:text-slate-600 dark:border-slate-700 dark:text-slate-500 dark:hover:text-slate-300"
                    : index < current
                      ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-200 dark:bg-emerald-950 dark:text-emerald-300"
                      : "bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700"
              }`}
            >
              {index + 1}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

/** The banner a locked step wears, plus the shortcut that unlocks it. */
function LockNotice({
  lock,
  onJump,
}: {
  lock: StepLock;
  onJump: (index: number) => void;
}) {
  return (
    <div
      role="status"
      className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-200"
    >
      <p>
        <strong className="font-medium">Preview only.</strong> {lock.reason}
      </p>
      <button
        type="button"
        onClick={() => onJump(lock.goToStep)}
        className="mt-2 rounded-md border border-amber-300 px-2.5 py-1 text-xs font-medium hover:bg-amber-100 dark:border-amber-800 dark:hover:bg-amber-900/50"
      >
        Go to step {lock.goToStep + 1}
      </button>
    </div>
  );
}

/**
 * A step you can read but not fill.
 *
 * WHY it draws its own disabled copy of the form instead of mounting the
 * real one behind a `disabled` prop: the live steps mount editors that
 * fetch on mount against a product id, and the step that is locked
 * precisely BECAUSE there is no product yet has no id to fetch with.
 * Showing the shape of the form is the whole ask; running it is not.
 *
 * The `disabled` sits on a <fieldset>, which natively disables every
 * control inside it -- one attribute, and nothing to keep in sync as
 * fields are added to the step spec.
 */
function LockedStepPreview({
  step,
  lock,
  vocabularies,
  onJump,
}: {
  step: ChildStepSpec;
  lock: StepLock;
  vocabularies: Vocabularies;
  onJump: (index: number) => void;
}) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600 dark:text-slate-400">{step.blurb}</p>
      <LockNotice lock={lock} onJump={onJump} />
      <Card>
        <fieldset disabled className="space-y-3 opacity-60">
          {step.fields.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {step.fields.map((spec) => (
                <div
                  key={spec.name}
                  className={spec.type === "textarea" ? "sm:col-span-2" : ""}
                >
                  <Field
                    spec={spec}
                    value={undefined}
                    vocabularies={vocabularies}
                    onChange={NO_OP}
                  />
                </div>
              ))}
            </div>
          ) : (
            // The three custom editors declare no field specs, so there is
            // no form to draw -- say what opens here rather than showing
            // an empty card.
            <p className="text-sm text-slate-500 dark:text-slate-400">
              This step is a table rather than a form. It opens once the step
              it depends on is done.
            </p>
          )}
          <button type="button" className={secondaryButtonClass}>
            {step.addLabel}
          </button>
        </fieldset>
      </Card>
    </div>
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

  // The generic add/delete form runs only for a step with no
  // `customEditor`, and every one of those names a factory-backed child
  // collection. P23's product information is the one step id that is not
  // one (it is a 1:1 PUT resource), so the narrowing lives here, once,
  // with its reason -- rather than as a cast at each of the three call
  // sites below.
  const resource = step.id as ProductChildResource;

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const saved = await api.createProductChild(productId, resource, draft);
      onSaved(resource, { ...draft, ...saved });
      setDraft({});
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    try {
      await api.deleteProductChild(productId, resource, id);
      onDeleted(resource, id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete");
    }
  }

  if (step.customEditor === "product-information") {
    // P23. The third non-generic step, and the first whose reason is not
    // tabular data: half of this screen is deliberately read-only, and a
    // field spec has no way to describe a value that is shown but not
    // yours to type. See ProductInformationEditor.tsx.
    return (
      <div className="space-y-4">
        <p className="text-sm text-slate-600 dark:text-slate-400">{step.blurb}</p>
        <ProductInformationEditor productId={productId} vocabularies={vocabularies} />
      </div>
    );
  }

  if (step.customEditor === "bioequivalence") {
    // P22. The second non-generic step, and for a different reason than
    // the first: the comparator is a row other rows point at (so it cannot
    // be a text field on the study without reintroducing the drift rule
    // R26 exists to catch), and the results are a fixed three-row table
    // saved as a set. See BioequivalenceEditor.tsx.
    return (
      <div className="space-y-4">
        <p className="text-sm text-slate-600 dark:text-slate-400">{step.blurb}</p>
        <BioequivalenceEditor productId={productId} />
      </div>
    );
  }

  if (step.customEditor === "drug-product-control") {
    // P21. The one step that is not the generic add-a-row form -- see
    // `ChildStepSpec.customEditor` for why, and StabilityGrid for what the
    // deviation costs.
    //
    // It also gives the FINISHED PRODUCT's control data its first home in
    // the wizard. P20 built 3.2.P.5.1 and 3.2.P.5.4 and mounted the editor
    // only under a drug substance and an excipient, so a filer could not
    // enter the drug product's own specification at all -- and without it
    // the stability grid has no limits to check against and nothing to
    // offer as rows. The panel is the same component the API rows use.
    return (
      <div className="space-y-4">
        <p className="text-sm text-slate-600 dark:text-slate-400">{step.blurb}</p>
        <Card>
          <OwnerControlPanel
            owner="drug-product"
            ownerId={productId}
            ownerName="this product"
            withBatches
          />
        </Card>
      </div>
    );
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
                <span>{step.summarise?.(row)}</span>
                <button
                  type="button"
                  onClick={() => remove(String(row.id))}
                  className="text-xs text-slate-500 hover:text-red-600"
                >
                  Remove
                </button>
              </div>
              {/* P20: an active ingredient carries its own 3.2.S.4.1 and
                  its own batches; an excipient carries its own 3.2.P.4.1.
                  Both sections repeat per subject, so the tables belong to
                  the subject, not to the product -- which is exactly why
                  the editor is nested inside the row rather than being a
                  step of its own. One editor serves both. */}
              {step.id === "apis" && (
                <OwnerControlPanel
                  owner="drug-substance"
                  ownerId={String(row.id)}
                  ownerName={String(row.inn_name ?? "this substance")}
                  withBatches
                />
              )}
              {step.id === "excipients" && (
                <SpecificationEditor
                  owner="excipient"
                  ownerId={String(row.id)}
                  ownerName={String(row.name ?? "this excipient")}
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

/**
 * A specification plus, where the CTD has one, the batches measured
 * against it.
 *
 * The two are one component because the batch screen needs the
 * specification's actual rows -- a result answers a test, and the tests
 * offered must provably be the same rows the editor above is showing. Two
 * independent fetches could disagree, and "the result answers a test in
 * the spec" is the invariant the whole screen exists to hold.
 */
function OwnerControlPanel({
  owner,
  ownerId,
  ownerName,
  withBatches = false,
}: {
  owner: "drug-substance" | "drug-product";
  ownerId: string;
  ownerName: string;
  withBatches?: boolean;
}) {
  const [specification, setSpecification] = useState<SpecificationTest[]>([]);
  const [batches, setBatches] = useState<BatchAnalysis[]>([]);
  return (
    <>
      <SpecificationEditor
        owner={owner}
        ownerId={ownerId}
        ownerName={ownerName}
        onRowsChange={setSpecification}
      />
      {withBatches && (
        <>
          <BatchAnalysisEditor
            owner={owner}
            ownerId={ownerId}
            ownerName={ownerName}
            specification={specification}
            onBatchesChange={setBatches}
          />
          {/* P21. The three screens are one component for one reason: a
              stability result answers a specification test and a study is
              run on a batch, so the grid needs both lists to be provably
              the same rows the editors above are showing. Fetching them
              again here could disagree, and "this result answers a test in
              the spec, at a batch in the dossier" is the invariant the
              whole panel exists to hold. */}
          <StabilityGrid
            owner={owner}
            ownerId={ownerId}
            ownerName={ownerName}
            specification={specification}
            batches={batches}
          />
        </>
      )}
    </>
  );
}

function Wizard() {
  const router = useRouter();
  const [vocabularies, setVocabularies] = useState<Vocabularies | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [productId, setProductId] = useState<string | null>(null);
  const [productDraft, setProductDraft] = useState<Draft>({});
  const [rows, setRows] = useState<SavedRows>({});
  const [projectDraft, setProjectDraft] = useState<Draft>({
    region: "NAFDAC",
    submission_type: "multisource-generic",
  });
  const [applicants, setApplicants] = useState<Applicant[]>([]);
  const [applicantId, setApplicantId] = useState<string>("");
  const [newApplicant, setNewApplicant] = useState<Draft>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .getEnums()
      .then(setVocabularies)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Could not load vocabularies"),
      );
    // Applicants are master data that outlive any one filing, so the last
    // step offers the ones you already have before asking you to retype
    // a company you have filed under before.
    api.listApplicants().then(setApplicants).catch(() => {});
  }, []);

  /**
   * Two of the wizard's selects cross-reference rows the user created in
   * an EARLIER step -- an active ingredient names its manufacturer (R17),
   * a batch-formula line names its active (R04). Those options cannot come
   * from /enums, because they are this product's own data, so they are
   * built here from what has been saved so far and merged over the static
   * vocabularies under names the field specs refer to.
   */
  const allVocabularies: Vocabularies | null = useMemo(() => {
    if (vocabularies === null) return null;
    // Typed by RuntimeVocabulary, so a key that no field spec refers to
    // (or a misspelling of one that does) is a compile error rather than
    // an empty dropdown.
    const runtime: Record<RuntimeVocabulary, EnumOption[]> = {
      manufacturer: (rows.manufacturers ?? []).map((row) => ({
        value: String(row.id),
        label: `${String(row.name ?? "site")} (${String(row.role ?? "")})`,
      })),
      active_ingredient: (rows.apis ?? []).map((row) => ({
        value: String(row.id),
        label: String(row.inn_name ?? "active ingredient"),
      })),
    };
    return {
      ...vocabularies,
      ...runtime,
    };
  }, [vocabularies, rows]);

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
      // R14 blocks export without an applicant, so the wizard captures one
      // here rather than leaving it to be discovered on the validation tab.
      let chosenApplicantId: string | null = applicantId || null;
      if (chosenApplicantId === null && newApplicant.company_name) {
        const created = await api.createApplicant(newApplicant);
        chosenApplicantId = created.id;
      }

      const project = await api.createProject({
        name: String(projectDraft.name ?? ""),
        region: String(projectDraft.region ?? "NAFDAC"),
        submission_type: String(
          projectDraft.submission_type ?? "multisource-generic",
        ),
        product_id: productId,
        applicant_id: chosenApplicantId,
      });
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the project");
    } finally {
      setBusy(false);
    }
  }

  // One rule, asked twice: for the step on screen, and once per circle in
  // the stepper. Both go through lockForStep, so the badge and the page
  // can never disagree about whether a step is open.
  const lockAt = (index: number) => lockForStep(index, productId !== null, rows);
  const stepLock = lockAt(stepIndex);

  if (error && vocabularies === null) return <ErrorNotice message={error} />;
  if (vocabularies === null || allVocabularies === null)
    return <p className="text-sm text-slate-500">Loading…</p>;

  const isProductStep = stepIndex === 0;
  const isReviewStep = stepIndex === TOTAL_STEPS - 1;
  const childStep = !isProductStep && !isReviewStep ? CHILD_STEPS[stepIndex - 1] : null;

  return (
    <>
      <PageHeading
        title="New product"
        subtitle="Capture the data. The dossier is generated from it — you never upload one."
      />
      <Stepper
        current={stepIndex}
        total={TOTAL_STEPS}
        lockAt={lockAt}
        onJump={setStepIndex}
      />

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

      {childStep && (
        <>
          <h2 className="mb-3 text-lg font-medium">{childStep.title}</h2>
          {productId !== null && stepLock === null ? (
            <ChildStep
              step={childStep}
              productId={productId}
              vocabularies={allVocabularies}
              rows={rows[childStep.id] ?? []}
              onSaved={handleSaved}
              onDeleted={handleDeleted}
            />
          ) : (
            <LockedStepPreview
              step={childStep}
              // Unreachable: lockForStep always returns a lock when there
              // is no product, so a null lock here implies an id. Spelled
              // out because the compiler cannot see that.
              lock={stepLock ?? PRODUCT_FIRST}
              vocabularies={allVocabularies}
              onJump={setStepIndex}
            />
          )}
        </>
      )}

      {isReviewStep && (
        <Card>
          <h2 className="mb-1 text-lg font-medium">Create the project</h2>
          <p className="mb-4 text-sm text-slate-600 dark:text-slate-400">
            A project files this product to one regulator. The region decides
            which Module 1 documents and which builders apply; the submission
            type decides how much of Modules 2–5 the dossier owes.
          </p>
          {stepLock !== null && (
            <div className="mb-4">
              <LockNotice lock={stepLock} onJump={setStepIndex} />
            </div>
          )}
          <form onSubmit={createProject} className="space-y-4">
            {error && <ErrorNotice message={error} />}
            {/* The whole form in one disabled fieldset when the step is
                locked -- see LockedStepPreview for why a fieldset rather
                than a `disabled` prop on each control. */}
            <fieldset
              disabled={stepLock !== null}
              className={`space-y-4 ${stepLock !== null ? "opacity-60" : ""}`}
            >
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

              <Field
                spec={{
                  name: "submission_type",
                  label: "Submission type",
                  type: "select",
                  vocabulary: "submission_type",
                  required: true,
                  // The one sentence that explains why this field exists at
                  // all: a generic does not repeat the originator's animal
                  // studies, so its dossier DECLARES those modules excluded
                  // rather than omitting them.
                  help:
                    "A multisource (generic) filing declares Modules 2.4–2.7, " +
                    "Module 4 and most of 5.3 not applicable, and files a cited " +
                    "statement in each. Change this and the section list changes.",
                }}
                value={projectDraft.submission_type}
                vocabularies={vocabularies}
                onChange={(name, value) =>
                  setProjectDraft((previous) => ({ ...previous, [name]: value }))
                }
              />

              <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
                <h3 className="mb-1 text-sm font-medium">Applicant</h3>
                <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
                  The legal entity submitting this filing — often a local agent
                  acting for a foreign manufacturer. Required before export
                  (rule R14), and reusable across your other filings.
                </p>

                {applicants.length > 0 && (
                  <div className="mb-3">
                    <label
                      htmlFor="applicant-select"
                      className="mb-1 block text-sm font-medium"
                    >
                      Use an existing applicant
                    </label>
                    <select
                      id="applicant-select"
                      value={applicantId}
                      onChange={(e) => setApplicantId(e.target.value)}
                      className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
                    >
                      <option value="">— create a new one below —</option>
                      {applicants.map((applicant) => (
                        <option key={applicant.id} value={applicant.id}>
                          {applicant.company_name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {applicantId === "" && (
                  <div className="grid gap-3 sm:grid-cols-2">
                    {APPLICANT_FIELDS.map((spec) => (
                      <Field
                        key={spec.name}
                        spec={spec}
                        value={newApplicant[spec.name]}
                        vocabularies={vocabularies}
                        onChange={(name, value) =>
                          setNewApplicant((previous) => ({ ...previous, [name]: value }))
                        }
                      />
                    ))}
                  </div>
                )}
              </div>
              <button type="submit" disabled={busy} className={buttonClass}>
                {busy ? "Creating…" : "Create project"}
              </button>
            </fieldset>
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
