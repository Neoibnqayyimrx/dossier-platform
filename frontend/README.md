# Frontend (P11)

Next.js (App Router) + TypeScript + Tailwind, talking to the FastAPI
backend. The wizard captures **structured data** — it never asks anyone to
upload a finished dossier. That inversion is the product's whole point.

## Running it

All three pieces have to be up, in this order:

```bash
# 1. Postgres (the API 500s on every request without it)
docker compose up -d db

# 2. API — bind IPv4 explicitly, see the gotcha below
cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3. This app
cd frontend && npm run dev        # http://localhost:3000
```

Sign in at `/login`. "Create account" registers and signs you in with the
same form — the backend has no roles or email verification (P02 kept auth
deliberately minimal), so a separate signup page would be the same form
with a different button.

To get a project to look at: `cd backend && uv run python -m scripts.seed_demo`.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Set in `.env.local`. **Inlined at build time**, so `npm run build` must be re-run after changing it. |

The backend's `CORS_ALLOW_ORIGINS` must contain whatever origin this app is
served from (it defaults to both `localhost:3000` and `127.0.0.1:3000`).

### Gotcha: `localhost` vs `127.0.0.1`

On a machine where `localhost` resolves to `::1` (IPv6) first, a backend
bound only to `127.0.0.1` is unreachable from the browser — Chromium tries
`::1:8000`, gets connection refused, and reports it as:

> No 'Access-Control-Allow-Origin' header is present on the requested resource.

which looks exactly like a CORS misconfiguration but isn't one. `curl` hides
this by silently falling back to IPv4. Two ways out, either is fine:

- bind the API to `0.0.0.0` and point `NEXT_PUBLIC_API_BASE_URL` at
  `http://127.0.0.1:8000` (what `.env.local` does here), or
- bind the API dual-stack and leave the URL on `localhost`.

The same misleading symptom appears whenever the API returns a **500**:
FastAPI's CORS middleware doesn't attach headers to unhandled-exception
responses, so a crashing endpoint also surfaces in the browser as a CORS
error. If you see that message, check the API log before touching CORS
config.

## Tests

```bash
npm test        # Vitest — API client, auth, severity styling, wizard specs
npm run lint
npm run build   # also type-checks
npm run e2e     # Playwright happy path — needs the full stack up
```

`npm run e2e` drives the **real** backend: it walks the wizard, approves a
narrative, checks that validation blocks the build, overrides with a
logged reason, then builds and downloads a package. It creates and deletes
its own project, so it leaves the database as it found it. If the API
isn't reachable it skips with a message rather than failing.

## Layout

```
src/
├── app/                     routes (App Router)
│   ├── login/               sign in / register
│   └── projects/            dashboard + per-project detail
├── components/              AuthGuard, SiteHeader, shared UI
└── lib/
    ├── api.ts               typed backend client + token storage
    ├── auth.tsx             AuthProvider / useAuth
    └── types.ts             mirrors of the backend's read schemas
```

Data is fetched in Client Components rather than Server Components: the
bearer token lives in `localStorage`, which the server cannot read. See the
comment at the top of `lib/api.ts` for the full reasoning and what would
have to change to move it server-side.
