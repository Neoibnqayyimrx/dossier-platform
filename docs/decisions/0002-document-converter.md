# 0002 — How DOCX→PDF conversion reaches LibreOffice

- **Status:** Accepted
- **Date:** 2026-09-18
- **Phase:** Phase 1a (DOCX→PDF rendering performance)
- **Supersedes:** the per-call `soffice` subprocess introduced in P07

---

## The measurement that drove this

Not a guess. Timing the existing `convert_docx_to_pdf` on documents of
different sizes:

| input | time |
|---|---|
| 1-paragraph `.docx` | **1109 ms** |
| 400-paragraph `.docx` | **1134 ms** |
| rendered 3.2.P.1 (37 KB, real template) | **1109 ms** |

399 extra paragraphs cost **25 ms**. Everything else — roughly **1.1 s of
every single conversion, about 98% of it** — was fixed cost paid before a
page was laid out:
forking `soffice`, building a throwaway user profile, registering
import/export filters, bootstrapping UNO.

A NAFDAC package converts one document per leaf and has dozens. The test
suite rebuilds packages constantly, which is why it took **1:11:14**.

### A wrong measurement worth recording

The first attempt timed `soffice --version` as a proxy for startup and got
**107 ms — 8% of a call**, which says "startup is not the problem" and would
have ended this phase. That proxy is wrong: `--version` prints and exits
without the filter and UNO bootstrap a real conversion pays for.

The honest probe is to convert *the smallest possible document through the
real code path*. Whatever that costs is the fixed overhead. Keep this in
mind the next time something is benchmarked here — measure the real path,
not a cheaper thing that resembles it.

## Decision

Three transports behind a `DocumentConverter` protocol
(`app/assembly/converter.py`), selected by `DOCUMENT_CONVERTER`:

1. **`libreoffice-listener` (default)** — one `soffice` process, started
   once and reused, driven through **`unoserver`**.
2. **`soffice-subprocess`** — the previous behaviour, retained.
3. **`gotenberg`** — HTTP to a Gotenberg container.

Rendering is unchanged in all three: it is the same LibreOffice engine. Only
the way we reach it differs. Determinism (pinned `/CreationDate`,
content-derived `/ID`, the explicit bookmark) stays in `pdf.py` and is
applied to every transport's output alike.

### Result

| transport | cold | warm |
|---|---|---|
| `soffice-subprocess` | ~1109 ms | ~1109 ms (every call is cold) |
| `libreoffice-listener` | ~5.9 s (includes starting the listener) | **185–237 ms** |

**6.0x faster per document, ~924 ms saved on each.** Measured on an idle
machine; an earlier run taken while another test suite saturated the box
(load average 9.7) inflated both sides ~5x but held the same ratio.

**Byte-identical output.** The listener and a fresh `soffice` produce the
same PDF, same MD5 (`55cdceb8…` on the 3.2.P.1 fixture), after
normalization. This is not a nicety: P09 checksums *are* hashes of these
bytes, and `resolve_lifecycle` decides `new` vs `replace` by comparing a
leaf's checksum across sequences. A transport that changed the output by one
byte would silently mark every unchanged document as modified in the next
sequence — a regulatory-visible defect. There is a test asserting this
equality (`test_the_listener_produces_byte_identical_output_to_a_fresh_soffice`).

## Why `unoserver` rather than a hand-rolled UNO bridge

Both were viable; the bridge is perhaps 150 lines. `unoserver` won on three
points, in order of weight:

1. **It keeps `uno` out of our process.** The client runs out of process, so
   the API worker never imports `uno`. That matters because pyuno is a
   compiled binding built against *the distribution's* Python, not ours —
   importing it into the API would couple our interpreter choice to the
   distro's. It also means a LibreOffice crash cannot take an API worker
   down with it.
2. **The fiddly part is the part that is easy to get wrong.** Filter names,
   document close semantics, the `com.sun.star.*` property dance. This is a
   maintained implementation of exactly that.
3. It is purpose-built for this pattern, so lifecycle concerns (the listener
   binding its port after forking `soffice`) are already handled.

The cost is one dependency plus ~100 ms per call for spawning the client
process. An in-process bridge would recover that ~100 ms. Not worth it
against point 1 — revisit only if conversion volume makes 100 ms matter.

## Operational consequences

- **`python3-uno` is a required system package**, not optional, wherever the
  listener runs. It cannot be pip-installed: it ships with LibreOffice. CI
  installs it explicitly, and checks it is importable as an early step so a
  mismatch fails with one legible message instead of a few hundred
  conversion errors.
- **Python ABI coupling — the sharp edge.** `python3-uno` is built for the
  distro's Python minor version. If the interpreter running `unoserver`
  differs (e.g. distro ships 3.12, the project pins 3.11), `import uno`
  fails and the listener will not start. `UNO_PYTHON_PATH` points at the
  distro's `dist-packages`; if the versions diverge, either align them or
  set `DOCUMENT_CONVERTER=soffice-subprocess` and accept the ~6x slowdown.
  **This is the most likely thing to break on a new platform.**
- **Conversions are serialized** by a lock. A single UNO listener is not
  safely reentrant — concurrent conversions through one bridge interleave
  document open/close and produce corrupt output or hangs. At ~200 ms a
  conversion this is not the bottleneck. If it ever becomes one, the answer
  is several listeners on separate ports, not removing the lock.
- **The listener binds a kernel-chosen free port** (`SOFFICE_LISTENER_PORT=0`,
  the default) rather than a fixed one. A fixed port looks tidier and is a
  trap: a listener orphaned by an earlier run still holds it, the next one
  cannot bind, and because that surfaces as a failed conversion rather than
  a bind error, the restart path turns it into a loop that spawns a new
  LibreOffice each time. Set an explicit port only when something outside
  the process must reach the listener.
- **A dead listener restarts automatically**, once, then the error
  propagates. Without this a single crash would fail every conversion for
  the rest of the process's life, since the converter is a process-wide
  singleton.
- **The listener starts lazily**, following this codebase's existing pattern
  for long-lived resources (`get_settings`, `get_storage_client`) rather
  than introducing a FastAPI lifespan handler where none exists. A
  deployment that never converts a document never starts LibreOffice.

## Why Gotenberg is included but not the default

It earns its place as the answer to "LibreOffice should not be in the API
container at all" — a read-only image, separate scaling, a managed
conversion service. It is a real, tested path, not a paragraph: there is a
test that exercises it against a running container and skips when none is
reachable, matching how the repo already treats optional services.

It is not the default because it requires infrastructure, and the listener
gets the same win with none. Opt in with
`docker compose --profile gotenberg up` and `DOCUMENT_CONVERTER=gotenberg`.

## Rejected

- **Replacing LibreOffice** (docx→PDF in pure Python, headless Word, a
  commercial SDK). The problem was never rendering fidelity, which is the
  reason LibreOffice was chosen in P07 and remains sound.
- **Raising the `lru_cache` size.** It already caches; it helps only for
  *identical* input, and a dossier's documents differ. Orthogonal, and kept.
- **Converting in parallel.** Would multiply the startup cost rather than
  remove it, and one listener cannot be driven concurrently anyway.
