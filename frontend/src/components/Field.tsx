"use client";

import type { FieldSpec } from "@/lib/wizard-steps";
import type { Vocabularies } from "@/lib/types";

const inputClass =
  "w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950";

export function Field({
  spec,
  value,
  vocabularies,
  onChange,
}: {
  spec: FieldSpec;
  value: unknown;
  vocabularies: Vocabularies;
  onChange: (name: string, value: unknown) => void;
}) {
  const id = `field-${spec.name}`;

  if (spec.type === "checkbox") {
    return (
      <label htmlFor={id} className="flex items-center gap-2 text-sm">
        <input
          id={id}
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(spec.name, e.target.checked)}
          className="rounded border-slate-300"
        />
        {spec.label}
      </label>
    );
  }

  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {spec.label}
        {spec.required && <span className="ml-0.5 text-red-600">*</span>}
      </label>

      {spec.type === "select" ? (
        <select
          id={id}
          required={spec.required}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(spec.name, e.target.value || null)}
          className={inputClass}
        >
          <option value="">—</option>
          {(vocabularies[spec.vocabulary ?? ""] ?? []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : spec.type === "textarea" ? (
        <textarea
          id={id}
          required={spec.required}
          rows={3}
          value={(value as string) ?? ""}
          placeholder={spec.placeholder}
          onChange={(e) => onChange(spec.name, e.target.value || null)}
          className={inputClass}
        />
      ) : (
        <input
          id={id}
          type={spec.type}
          required={spec.required}
          value={(value as string | number) ?? ""}
          placeholder={spec.placeholder}
          onChange={(e) =>
            onChange(
              spec.name,
              spec.type === "number"
                ? // An empty number input must send null, not NaN or 0 --
                  // "not captured yet" is a real state the data model
                  // represents with NULL, and 0 would be a claim.
                  e.target.value === ""
                  ? null
                  : Number(e.target.value)
                : e.target.value || null,
            )
          }
          className={inputClass}
        />
      )}

      {spec.help && (
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {spec.help}
        </p>
      )}
    </div>
  );
}
