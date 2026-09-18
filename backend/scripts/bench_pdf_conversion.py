"""Benchmark DOCX->PDF conversion: how much is process startup, how much
is the actual conversion?

Phase 1a Step 1. The hypothesis under test is that cold-starting
LibreOffice dominates, so the fix is to stop paying startup per call
rather than to replace the rendering engine.

Run:  .venv/bin/python -m scripts.bench_pdf_conversion
"""

from __future__ import annotations

import io
import statistics
import time

from app.assembly.pdf import clear_conversion_cache, convert_docx_to_pdf

REPEATS = 5


def _sample_docx() -> bytes:
    """A real rendered section, not a synthetic one-liner: the point is to
    time a document the platform actually produces. Uses the EXAMOX seed,
    built in memory -- no database needed, since render_section only reads
    the object graph."""
    from app.core.storage import InMemoryStorageClient
    from app.seed.examox import build_examox
    from app.templating.render import render_section

    project = build_examox(buggy=False)
    storage = InMemoryStorageClient()
    # 3.2.P.1 (composition) is representative: a table, headings, prose.
    for number in ("3.2.P.1", "2.3", "1.0"):
        try:
            result = render_section(number, project, storage=storage)
        except Exception as exc:  # noqa: BLE001 - try the next candidate
            print(f"  ({number} did not render: {type(exc).__name__}: {exc})")
            continue
        print(f"  using section {number}")
        return storage.get(result.storage_key)
    raise SystemExit("could not render a sample section; adjust the script")


def _minimal_docx(paragraphs: int) -> bytes:
    """The honest startup probe.

    WHY not `soffice --version`: the first version of this script timed that
    and concluded startup was only 8% of a call, which is wrong --
    `--version` prints and exits without the filter/UNO bootstrap a real
    conversion pays for. Converting the SMALLEST POSSIBLE document through
    the real code path is the correct probe: whatever it costs is fixed
    overhead, because there is almost nothing to lay out.
    """
    from docx import Document

    document = Document()
    for i in range(paragraphs):
        document.add_paragraph(f"para {i}")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _time(converter, docx: bytes, reps: int = REPEATS) -> list[float]:
    samples = []
    for _ in range(reps):
        start = time.perf_counter()
        converter.convert(docx)
        samples.append(time.perf_counter() - start)
    return samples


def _report(label: str, samples: list[float]) -> float:
    median = statistics.median(samples)
    print(
        f"{label:<34} median {median * 1000:8.1f} ms   "
        f"min {min(samples) * 1000:8.1f}   max {max(samples) * 1000:8.1f}"
    )
    return median


def main() -> None:
    from app.assembly.converter import (
        LibreOfficeListenerConverter,
        SofficeSubprocessConverter,
    )

    print(f"Rendering a sample section... (repeats={REPEATS})")
    real = _sample_docx()
    tiny = _minimal_docx(1)
    big = _minimal_docx(400)
    print(f"real section .docx = {len(real):,} bytes\n")

    subprocess_converter = SofficeSubprocessConverter()
    listener = LibreOfficeListenerConverter(port=2007)

    try:
        print("--- one fresh soffice per call (the old behaviour) ---")
        m_tiny = _report("  1-paragraph doc", _time(subprocess_converter, tiny))
        m_big = _report("  400-paragraph doc", _time(subprocess_converter, big))
        _report("  real 3.2.P.1 section", _time(subprocess_converter, real))
        print(
            f"  => fixed overhead ~{m_tiny * 1000:.0f} ms; "
            f"399 extra paragraphs cost only {(m_big - m_tiny) * 1000:.0f} ms"
        )
        if m_tiny / m_big > 0.5:
            print("  => startup DOMINATES; a persistent listener is the right fix.\n")
        else:
            print("  => startup does NOT dominate; do not change the transport.\n")

        print("--- persistent listener (unoserver) ---")
        listener.convert(tiny)  # pay the one-time start outside the timing
        l_tiny = _report("  1-paragraph doc", _time(listener, tiny))
        _report("  400-paragraph doc", _time(listener, big))
        l_real = _report("  real 3.2.P.1 section", _time(listener, real))

        print()
        print(f"speedup, trivial doc : {m_tiny / l_tiny:.1f}x")
        print(f"per-document saving  : ~{(m_tiny - l_tiny) * 1000:.0f} ms")
        print(f"real section now     : {l_real * 1000:.0f} ms")

        clear_conversion_cache()
        convert_docx_to_pdf(real, bookmark_title="B")
        start = time.perf_counter()
        convert_docx_to_pdf(real, bookmark_title="B")
        print(f"lru_cache hit        : {(time.perf_counter() - start) * 1000:.2f} ms")
    finally:
        listener.shutdown()


if __name__ == "__main__":
    main()
