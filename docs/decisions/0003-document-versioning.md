# 0003 — Where a document's version history lives

- **Status:** Accepted
- **Date:** 2026-09-20
- **Phase:** Phase 2 (document versioning)
- **Supersedes:** the "no version history" simplification recorded in P18

---

## The question

P18 attached real files to leaves and deliberately did not version them:
re-uploading overwrote the row *and* the object-storage bytes. The
justification, written into `section_document.py`, was that eCTD lifecycle
already versions at the **sequence** level, so the history a regulator sees
is preserved by checksums even though the working copy's is not.

That argument is half right, and the missing half is the point of this
phase. Sequence-level history covers what was **filed**. Between two
sequences a leaf can be replaced any number of times, and each replacement
destroyed its predecessor irrecoverably. So these had no answer:

- *"Which CPP did we attach in March, and who replaced it in April?"*
- *"The assessor's copy of 3.2.S.3.1 differs from ours — when did it change?"*
- *"Show me the bioequivalence report the filed one replaced."*

A dossier is a regulated record. "We overwrote it" is not an answer.

## Decision

A separate **`document_version`** table, one immutable row per upload, with
its own `storage_key`, `md5`, `size_bytes`, `original_filename`,
`content_type`, `uploaded_by_id`, `uploaded_at`, and a `version_number`
unique per `section_document`.

**`SectionDocument` stays the current version** and keeps its file columns,
rather than being folded into the version table behind an `is_current` flag.

### Why not the `is_current` flag

Both shapes were viable. Three things decided it:

1. **Every consumer already reads the document.** `app/assembly/assemble.py`
   (twice), the lifecycle resolver, and the validation rules all reach for
   `document.storage_key` and `document.md5`. Folding the columns into a
   version table means each of them learns about versioning to keep doing
   exactly what it does now. The phase brief's own requirement — "the eCTD
   lifecycle resolver must keep working unchanged" — points the same way.
2. **The uniqueness constraint stays unconditional.** `UniqueConstraint
   (project_id, section_number, subject_slug)` is what stops two files
   landing at one leaf, which would put a duplicate entry in the package's
   zip. Under `is_current` that has to become a partial index over
   `is_current = true`, which is a conditional guarantee where an
   unconditional one exists today.
3. **It matches how the dossier is actually read.** A leaf holds one
   document. Its history is audit metadata *about* that leaf, not a set of
   equal candidates one of which happens to be flagged.

### The cost, stated plainly

The file columns on `SectionDocument` are a **denormalisation** of the
newest version row. Two places hold the same five values, and nothing in
the schema forces them to agree. That is a real cost and the honest name
for it is duplication.

What makes it acceptable: the invariant is narrow ("these columns equal
this document's highest-numbered version"), there is exactly one writer
(the upload route), and there is a test asserting it directly —
`test_the_document_row_always_describes_its_newest_version`. If a second
writer ever appears, revisit this.

## Every version gets its own storage key

Under P18 each upload wrote to one deterministic key,
`projects/{id}/documents/{leaf}.pdf`, so a replacement overwrote its
predecessor in the bucket. Version rows pointing at a key whose bytes had
since been replaced would be **a history that lies** — worse than having
none.

New uploads write to
`projects/{id}/documents/versions/{leaf}/v{n}.pdf`, still under the
`projects/{project_id}/` prefix that `artifacts.py` enforces as the
authorization boundary.

This was safe to change only because `storage_key_for` is called in exactly
one place (inside `ingest_document`) and every consumer *reads*
`document.storage_key` rather than reconstructing it. Verified before
changing it, not assumed.

**Backfilled rows keep the old key.** A pre-P26 document's version 1 points
at the deterministic path, because that is where its bytes really are.
Rewriting it to look like the new convention would put a false statement in
the audit trail this table exists to provide.

## Concurrency

Two uploads to the same leaf can both read `max(version_number)` and both
claim the next one — the same read-then-insert race closed for sequence
numbers in gap Phase 1, and closed the same way: the unique constraint is
the guarantee, a bounded retry is the recovery, and a 503 rather than a
version number we cannot prove is unique.

One difference worth recording: the losing upload has already written its
bytes to storage under a key nothing ends up referencing. That is wasted
space, not corruption, and it is much the better failure — the alternative
is two rows claiming to be version 3.

## Consequences

- Deleting a `SectionDocument` cascades to its versions. The working
  history goes with the leaf; the regulator-facing history lives in the
  sequences and is unaffected.
- An identical re-upload still records a version. Someone re-attaching the
  same file is a real event, and equal checksums are what tell a reader
  nothing changed — information the history should carry, not discard.
- `GET .../versions` lists oldest-first with `is_current` on each entry, so
  a caller never has to know which end of the list is current.
- The bytes endpoint reads the key off the **row**, never rebuilding it
  from the URL: a document endpoint handing back the wrong document is the
  worst failure this system has.

## The lifecycle regression

Proven on the **amlodipine** worked example the phase brief names —
`app/seed/amlodipine.py`, the filed Me Cure dossier behind
`docs/target-toc.yaml` and the subject of `tests/test_worked_example.py`.

`test_replacing_an_uploaded_document_still_drives_the_lifecycle` builds a
sequence from an uploaded leaf, replaces the document the way the upload
route does, and asserts that the next sequence files it as `replace`,
carries a `modified-file` back-reference, ships the **new** checksum, and
leaves version 1's bytes retrievable.

That last chain is the whole risk of this phase in one test: if the
resolver had read anything but the current version, a replaced document
would have filed as unchanged and the agency would never have received the
new file.
