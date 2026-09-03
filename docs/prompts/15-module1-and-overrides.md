# P15 — Module 1 completion and the override path

**Before starting:** read `AGENTS.md` (§5 cross-cutting rules, §6 data model), `reference/dossier-anatomy.md` on Module 1, and the **P14** entry in `reference/build-log.md`. Depends on P08 (the models and renderers already exist) and P14 (ownership).

## Goal

Make a NAFDAC dossier **finishable in the browser**. Today it cannot be: R13, R14 and R16 block every export, and the data that would clear them has no way into the system at all.

## The problem, stated precisely

A product created through the wizard, filled in completely, reaches this and stops:

```
ERROR R13  No Certificate of Pharmaceutical Product (CPP) on file
ERROR R14  No applicant on file
ERROR R16  Missing declarations: power-of-attorney, declaration-of-authenticity
→ POST /build/ctd  409
```

`Applicant`, `Certificate` and `Declaration` all have models, and
`app/templating/{certificates,declarations}.py` already render them into the
package. What is missing is any way to create a row: no schemas, no routers,
no UI. Two more collections (`clinical`, `batch-formula`) have endpoints but
no wizard step, so R06 and R04 are unreachable from the browser too.

This is one phase rather than five fixes because every item is the same
shape — a modelled entity with no way in — and they all block the same
build.

## Tasks

### P15a — Module 1 data in (backend)

1. **Applicant ownership.** `Applicant` is master data reused across a
   user's projects, so it needs an `owner_id` exactly like `Product`
   (migration + schemas + `/applicants` CRUD filtered by owner). Rejected
   alternatives, for the record: nesting it under Project (reuse across
   projects then needs a list endpoint, which needs an owner filter, which
   is this option); and leaving it global (the `/kb/ingest` mistake — an
   unowned, editable, shared table).
   Linking a project to an applicant must verify the applicant is *yours*,
   the same way `create_project` verifies the product is.
2. **Certificates** — `/products/{id}/certificates` through the existing
   child-router factory. No new pattern; Certificate is product-scoped.
3. **Declarations** — the first collection whose parent is `Project`, not
   `Product`. `build_child_router`'s `owner_via` walks one relationship;
   this needs two hops (Declaration → Project → Product → owner). Teach
   `owner_via` to accept a path (`"project.product"`) rather than adding a
   second factory — one factory that drifts from itself is the thing to
   avoid.
4. **Ownership probes** for every new collection, added to the tables in
   `tests/test_ownership.py`. A new endpoint without a probe is the exact
   regression that file exists to catch.

### P15b — the wizard learns the rest of the data

5. **Two missing wizard steps** for collections the API already serves:
   clinical (unblocks R06 for a generic) and batch formula (R04, and the
   composition table 3.2.P.1 actually needs it).
6. **A Module 1 step**: applicant (pick an existing one or create), CPP
   certificate with its expiry date (R13 checks the date, not just the
   row), and declarations with their `signed` / `notarized` flags (R15
   checks the flags — an unsigned declaration is worse than a missing one).
7. **Region-aware, from the backend profile.** NAFDAC asks for a CPP, a
   Power of Attorney and a Declaration of Authenticity; FDA/EU Module 1 is
   a different list. The UI must not hard-code that — serve the required
   Module 1 items from the region profile, the same way `/enums` and
   `/sections` already refuse to let the frontend keep a second copy of
   the truth.

### P15c — the override, made honest

8. **Withdrawal without deletion.** Overrides can currently be created and
   never taken back, which pushes people away from using the feature
   properly. Add `withdrawn_at` / `withdrawn_by_id` and an endpoint; the
   engine ignores withdrawn rows. Append-only: a withdrawal is a new
   logged fact, never a hard delete, because the audit trail is the whole
   control.
9. **UI for any project owner**, not for admins. Reason mandatory
   (enforce a minimum length server-side — "n/a" is not a reason), showing
   who logged it and when, with a withdraw action.
   *Why not admin-gated:* `UserRole.ADMIN` means "may manage accounts", and
   overloading it with regulatory sign-off authority makes one bit mean two
   unrelated jobs. Segregation of duties — the author of the data should
   not be the sole approver of bypassing a check on it — is a real
   principle, but it needs a **project-scoped** role (author/approver), not
   the account-administration bit. With one user per dossier, an admin gate
   would only mean the same person promotes themselves: theatre, which is
   worse than an honest open control. Revisit when the platform has
   several people per organisation.
10. **Loud in the package.** An override currently lives only in the
    database. List overrides in the build response and render them into the
    package itself (alongside the TOC), so whoever opens the ZIP sees which
    deterministic checks were waived, by whom, and why. Detection over
    prevention: the control on an override is visibility, not permission.

## Definition of done

- A NAFDAC dossier goes from empty to downloaded package **entirely in the
  browser, with no overrides**, given real data. (The demo seed stays
  deliberately buggy — do not "fix" it to make this pass.)
- Every new collection has intruder probes in `test_ownership.py`.
- An override can be recorded, seen, withdrawn, and appears in the built
  package.
- `pytest -q`, `ruff`, `black --check` green; frontend `lint`, `tsc`,
  `vitest` green; the Playwright happy path still passes.

## Design notes

- **Nothing here is LLM work.** Certificates are third-party proof the
  platform must never generate; declarations are generated but only real
  once a human signs them. Both already render correctly — this phase adds
  the data, not the documents.
- **Placement is already settled** (P08) and is not reopened: applicant on
  Project (the same product is filed by different entities in different
  markets), certificate on Product (a CPP attests to the medicine, and
  survives re-filing), declaration on Project (a Power of Attorney names a
  representative for *this* submission).
- 404-not-403 continues everywhere a resource is not yours.

## On completion

Tick **P15** in `AGENTS.md` §7; append to `reference/build-log.md` — including
whatever the build teaches that this plan got wrong.
