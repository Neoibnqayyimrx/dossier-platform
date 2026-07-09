# P11 — Frontend: Product Wizard, Dashboard, Validation Viewer

**Before starting:** read `AGENTS.md` (§1 the flow, §3). If a frontend design skill is available, consult it. Depends on P02–P10 (consumes the API).

## Goal

Give the platform a usable face: a wizard that captures structured product data (not documents), a project dashboard, narrative review, a validation report viewer, and build/download for CTD and eCTD.

## Tasks

1. **Next.js + TypeScript + Tailwind** app in `frontend/`, talking to the FastAPI backend. Auth flow (login, token storage, protected routes).
2. **Product Information Wizard** — multi-step form mirroring the data model (`AGENTS.md` §6): Product → Manufacturer(s) → API(s) → Excipients → Packaging → Stability → Clinical. Structured inputs with the controlled vocabularies from P01 (dosage form, GMP status, registration type, etc.). Save-as-you-go; validate inputs client-side, but trust the server as source of truth.
3. **Project dashboard** — per project: region, completeness, a readiness summary (from `/readiness`), and quick actions.
4. **Narrative review UI** — for each section's narrative slots: generate (P05), see the draft with its cited sources, edit, approve. Unapproved slots visibly flagged. Show the audit trail.
5. **Validation viewer** — render the consolidated report (P06/P10): errors vs warnings vs advisory AI findings, grouped by category, each naming the offending values, with a path to fix. Show the export gate status.
6. **Build & download** — trigger `build/ctd` and `build/ectd`, show progress, download the ZIP, view the manifest. Disable eCTD build for a NAFDAC-only project; disable builds while errors are unresolved.
7. **Region awareness** — the UI adapts Module 1 fields and available builders to the project's region profile.
8. **Tests** — Vitest for components; a Playwright happy-path: create project → fill wizard → generate+approve a narrative → run validation → build CTD → download.

## Definition of done

- A user can go from empty project to downloaded CTD package entirely through the UI, for the demo product.
- Validation errors are clearly shown and block export; warnings/AI findings are distinguishable.
- Narrative can only be approved through explicit review; unapproved narrative is visibly flagged.

## Design notes

- The wizard captures **data**, never asks the user to "upload a finished dossier". That inversion is the product's whole point.
- Keep region logic driven by the project's profile, matching the backend.

## On completion

Tick **P11** in `AGENTS.md` §7; append to `reference/build-log.md`.
