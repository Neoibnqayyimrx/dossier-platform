# 0004 — The organization is the unit of access

- **Status:** Accepted
- **Date:** 2026-09-23
- **Phase:** gap Phase 6a (organizations)
- **Supersedes:** the per-user ownership introduced in P14a

---

## The question

Since P14a, access has been decided by one column: `Product.owner_id`. You
reach a product if you created it, and nobody else ever does. Applicant
(P15a) added a second owned root on the same rule. Every ownership check in
the API is a variation of `WHERE owner_id = :current_user`.

That is a coherent rule, and it is the wrong one for what this platform is
for. A regulatory dossier is not a personal document. A single NAFDAC or
FDA filing is worked by a department: the RA lead who owns the submission,
the CMC writer who fills 3.2.S and 3.2.P, the QA reviewer who signs the
declarations, the publisher who assembles the sequence. The regulator does
not deal with any of them individually — the **applicant company** is the
legal entity responsible for the filing, and FDA's own Module 1 backbone
identifies it by a company-level D-U-N-S number (gap Phase 4b), not by a
person.

So per-user ownership made the platform single-seat by construction: the
only way for a colleague to see a dossier was to share an account.

## Decision

An **`Organization`** row is the tenant. `User`, `Product` and `Applicant`
each carry `organization_id`, and every ownership check compares the
caller's organization to the row's:

```sql
-- before                          -- after
WHERE Product.owner_id = :user     WHERE Product.organization_id = :user_org
```

`owner_id` stays on Product and Applicant, demoted to **who created it** —
an audit fact, never consulted for access.

Four decisions were put to the project owner, who chose all four
recommendations:

1. **One organization per user** (`User.organization_id`), not a membership
   table. A consultant serving two companies holds two accounts.
2. **Existing data migrates to one organization per existing user**, so
   nobody can see anything after the migration that they could not see
   before it.
3. **A platform super-admin exists, for accounts only.**
4. **Sequences stay on Project** (the `Application` entity, 6b, sits above
   Project without taking them).

### Why roles are not the access rule

`UserRole` is now scoped to the organization: an ADMIN manages its members,
a USER works its dossiers. An admin reads **exactly** what a user of the
same organization reads. Administration has never been a data bypass here
(P14b), and that line is the reason the role can stay a simple column
rather than growing into per-section permissions.

### Why a `is_superadmin` flag, not a third role

Platform-wide account administration is orthogonal to the role someone
holds inside their own organization: a super-admin is also a member
somewhere, with colleagues and dossiers of their own. Modelling it as a
third `UserRole` value would force those two facts into one column and make
"admin of my org" and "admin of the platform" indistinguishable in every
query that reads the role.

The flag grants:

- creating organizations, each with its first admin (an organization with
  no admin would be born locked out);
- listing and fixing accounts across organizations — the answer to *"our
  only admin left the company"*, which nothing inside that organization can
  solve;
- writing to the **global** knowledge base (`/kb/ingest`).

It grants **no dossier access**. No ownership check anywhere reads
`is_superadmin`, and `test_a_superadmin_reads_no_other_organizations_dossier`
asserts the same 404 a stranger gets.

### Why registration creates an organization

Signing up makes a new organization and makes you its ADMIN. The
alternative — joining an existing organization by naming it — would mean
anyone could register their way into a company's dossiers. Joining is
therefore always the receiving organization's decision: its admin creates
the account (`POST /admin/users`) and hands over a first password.

A consequence worth stating plainly: **the org-admin role is now
self-service** (register, and you are one). That is exactly why
`/kb/ingest` moved from `require_admin` to `require_superadmin` in this
phase. Any gate on something *shared between organizations* that still
accepted an org admin would now accept everybody.

### Why the migration is safe

One organization per existing user, holding precisely the products and
applicants that user owned, with each becoming its ADMIN. With one member
per organization, "the owner" and "the owner's organization" name the same
people, so no row changes hands. Former **global** admins become
super-admins, which is what the global role already meant. The downgrade
restores the old roles exactly, because the mapping is reversible: a user
was a global ADMIN if and only if they are now a super-admin.

`test_the_gap6a_migration_gives_each_existing_user_their_own_organization`
asserts that against rows inserted at the previous revision.

## Consequences

- **Deleting an account no longer orphans a dossier.** The organization
  holds it; `owner_id` is only a record of who created the row.
- **`tests/test_ownership.py` doubled rather than loosened.** Every stranger
  probe now runs twice — as an account in another organization, and as a
  super-admin of another organization — and every probe the owner replays,
  a colleague replays too. Without that colleague mirror, a check still
  comparing user ids would pass the whole file.
- **No organization switcher, by decision 1.** A person who works for two
  companies keeps two logins. If that becomes a real complaint, the
  membership table is the change, and it is a bigger one: `organization_id`
  on User becomes a join, and every check in this ADR becomes a subquery.
- **The super-admin has no UI.** It is an operator role, like the first
  admin before it: `scripts/promote_admin.py` grants the flag, and the
  `/superadmin` endpoints are reachable from the API only. Building a
  console for it would be the first screen in this codebase that shows one
  organization's data to someone outside it, and nothing yet needs it.
