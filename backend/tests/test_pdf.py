"""Tests for app.assembly.pdf: LibreOffice-backed DOCX->PDF conversion,
normalized to be byte-deterministic, text-searchable, and bookmarked.

These call the real `soffice` binary (no mocking the conversion itself --
the whole point of this module is that the actual LibreOffice output
becomes deterministic after normalization, which can only be verified by
actually running it).
"""

from __future__ import annotations

import io
import time

import pytest
from pypdf import PdfReader

from app.assembly.pdf import PdfConversionError, convert_docx_to_pdf

TEMPLATE = "templates/section_3_2_p_1.docx"


def _docx_bytes() -> bytes:
    with open(TEMPLATE, "rb") as f:
        return f.read()


def test_conversion_produces_a_valid_searchable_pdf():
    pdf_bytes = convert_docx_to_pdf(_docx_bytes())
    assert pdf_bytes[:5] == b"%PDF-"

    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    text = reader.pages[0].extract_text()
    assert "3.2.P.1" in text  # real extractable text, not a rasterized image


def test_conversion_is_not_encrypted_and_embeds_fonts():
    reader = PdfReader(io.BytesIO(convert_docx_to_pdf(_docx_bytes())))
    assert reader.is_encrypted is False
    resources = reader.pages[0].get("/Resources")
    fonts = resources.get("/Font") if resources else None
    assert fonts, "expected at least one embedded font resource"
    for ref in fonts.values():
        descriptor = ref.get_object().get("/FontDescriptor")
        assert descriptor is not None
        d = descriptor.get_object()
        assert any(k in d for k in ("/FontFile", "/FontFile2", "/FontFile3"))


def test_bookmark_title_is_set_from_the_caller_not_guessed():
    pdf_bytes = convert_docx_to_pdf(_docx_bytes(), bookmark_title="My Section Title")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    titles = [entry["/Title"] for entry in reader.outline]
    assert titles == ["My Section Title"]  # exactly one, no LibreOffice-added duplicate


def test_no_bookmark_when_none_requested():
    pdf_bytes = convert_docx_to_pdf(_docx_bytes(), bookmark_title=None)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert reader.outline == []


def test_converting_the_same_docx_twice_is_byte_identical():
    data = _docx_bytes()
    first = convert_docx_to_pdf(data, bookmark_title="3.2.P.1")
    second = convert_docx_to_pdf(data, bookmark_title="3.2.P.1")
    assert first == second


def test_missing_soffice_binary_raises_a_clean_error(monkeypatch):
    # NOTE: LibreOffice is remarkably tolerant of garbage input -- feeding
    # it plain garbage bytes or even random binary data does NOT reliably
    # fail (it falls back to interpreting it as some format rather than
    # erroring), so "bad input" isn't a meaningful failure case to test.
    # The realistic failure mode is the binary itself being missing/broken.
    #
    # P1a: asserted against SofficeSubprocessConverter directly rather than
    # through convert_docx_to_pdf. The default transport is now the
    # persistent listener, which reaches LibreOffice through unoserver and
    # so fails differently (see the test below); this one still covers the
    # path it always covered, which is the one that shells out to `soffice`.
    import subprocess

    from app.assembly.converter import SofficeSubprocessConverter

    def _raise_not_found(*args, **kwargs):
        raise FileNotFoundError("soffice not found")

    monkeypatch.setattr(subprocess, "run", _raise_not_found)
    with pytest.raises(PdfConversionError, match="not installed"):
        SofficeSubprocessConverter().convert(_docx_bytes())


def test_a_missing_unoserver_raises_a_clean_error(monkeypatch):
    """The listener's equivalent failure: the client binaries are absent.

    Must name the fix, not just fail -- a missing `unoserver` is an install
    problem, and the error says so and names the escape hatch.
    """
    import shutil

    from app.assembly.converter import LibreOfficeListenerConverter

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr("pathlib.Path.exists", lambda self: False if "uno" in self.name else True)

    with pytest.raises(PdfConversionError, match="unoserver"):
        LibreOfficeListenerConverter(port=2099).convert(_docx_bytes())


def test_the_listener_produces_byte_identical_output_to_a_fresh_soffice():
    """The fidelity claim the whole phase rests on.

    P09's checksums are hashes of these exact bytes, and a lifecycle
    operation compares a leaf's checksum across sequences -- so a transport
    change that altered the output by even one byte would silently mark
    every unchanged document as modified in the next sequence. Byte
    equality, not "looks the same", is the requirement.
    """
    from app.assembly.converter import LibreOfficeListenerConverter, SofficeSubprocessConverter
    from app.assembly.pdf import _normalize_pdf

    docx = _docx_bytes()
    listener = LibreOfficeListenerConverter()  # auto port, like production
    try:
        try:
            via_listener = listener.convert(docx)
        except PdfConversionError as exc:
            pytest.skip(f"no LibreOffice listener available here: {exc}")
        via_subprocess = SofficeSubprocessConverter().convert(docx)

        assert _normalize_pdf(via_listener, bookmark_title="3.2.P.1") == _normalize_pdf(
            via_subprocess, bookmark_title="3.2.P.1"
        )
    finally:
        listener.shutdown()


def test_a_dead_listener_is_restarted_rather_than_failing_every_later_call():
    """WHY this matters more than it looks: the listener is a process-wide
    singleton, so without automatic restart a single crash would fail every
    conversion for the rest of the process's life -- the API would keep
    accepting builds and keep failing them until someone restarted it.
    """
    from app.assembly.converter import LibreOfficeListenerConverter

    baseline = _count_soffice()
    converter = LibreOfficeListenerConverter()  # auto port, like production
    try:
        docx = _docx_bytes()
        try:
            first = converter.convert(docx)
        except PdfConversionError as exc:
            pytest.skip(f"no LibreOffice listener available here: {exc}")

        # Kill it the way a crash would, behind the converter's back.
        converter._process.kill()
        converter._process.wait(timeout=30)

        second = converter.convert(docx)
        assert second[:5] == b"%PDF-"
        assert len(second) == len(first)
    finally:
        converter.shutdown()

    # Regression (the fix after gap Phase 5): the crashed listener's own
    # LibreOffice used to outlive it. The restart spawned a replacement
    # beside it, and shutdown could not find the old group because it asked
    # the dead, reaped leader for its group id. Nothing may survive either.
    for _ in range(20):
        if _count_soffice() <= baseline:
            break
        time.sleep(1)
    assert _count_soffice() <= baseline, "a crashed listener's LibreOffice outlived it"


def test_gotenberg_converter_matches_the_local_converters():
    """Gotenberg is a real option, so it gets a real test.

    Skips when no Gotenberg is reachable, following the same pattern as the
    Postgres-backed fixtures in conftest.py: an optional service must never
    make `pytest -q` fail on a machine that hasn't opted in. Bring one up
    with `docker compose --profile gotenberg up -d gotenberg`.

    WHY it asserts on the NORMALIZED bytes rather than raw output: Gotenberg
    runs its own LibreOffice build, so its raw PDF carries different
    metadata and object ordering. What the platform actually requires is
    that the deterministic contract in pdf.py holds for every transport --
    a valid, non-encrypted, correctly bookmarked PDF with pinned dates.
    """
    import httpx

    from app.assembly.converter import GotenbergConverter
    from app.assembly.pdf import _normalize_pdf

    converter = GotenbergConverter()
    try:
        httpx.get(f"{converter._base_url}/health", timeout=3.0)
    except httpx.HTTPError as exc:
        pytest.skip(f"no Gotenberg reachable ({exc}); `docker compose --profile gotenberg up -d`")

    # WHY a retry rather than trusting /health: Gotenberg reports healthy
    # before its LibreOffice pool can actually convert, so the first request
    # after `docker compose up` can fail while the container is still
    # warming. Observed exactly once, immediately after starting it. One
    # retry removes the flake without hiding a genuine failure.
    try:
        raw = converter.convert(_docx_bytes())
    except PdfConversionError:
        time.sleep(5)
        raw = converter.convert(_docx_bytes())
    pdf = _normalize_pdf(raw, bookmark_title="3.2.P.1")

    assert pdf[:5] == b"%PDF-"
    reader = PdfReader(io.BytesIO(pdf))
    assert not reader.is_encrypted
    assert len(reader.pages) >= 1
    assert [item.title for item in reader.outline] == ["3.2.P.1"]
    # Determinism survives the different transport.
    assert reader.metadata.get("/CreationDate") == "D:20000101000000+00'00'"


def _count_soffice() -> int:
    """LIVE LibreOffice processes: soffice.bin and its launcher, oosplash.

    Live only, since the fix after gap Phase 5: this used to count zombies
    too, and in a container whose PID 1 never reaps (this devcontainer),
    every LibreOffice ever killed stays a zombie -- so the count crept up
    through a run and the test failed at random, for processes that were
    already dead. And oosplash as well as soffice.bin, because a live,
    SIGTERM-blocking oosplash is what actually leaked.
    """
    import subprocess

    out = subprocess.run(["ps", "-eo", "stat=,comm="], capture_output=True, text=True).stdout
    return sum(
        1
        for line in out.splitlines()
        if (parts := line.split())
        and not parts[0].startswith("Z")
        and parts[-1] in ("soffice.bin", "oosplash")
    )


def test_shutting_down_a_listener_leaves_no_orphaned_libreoffice():
    """Regression: shutdown() used to orphan the `soffice` it forked.

    How it announced itself: not an error, but a HANG, plus six LibreOffice
    processes at ~20% CPU each that outlived the run that created them. Two
    causes, both fixed -- unoserver's `--uno-port` defaults to 2002 for
    EVERY instance (so separate listeners fought over one port), and
    terminating the unoserver parent left its soffice child running.

    A leak like this is invisible in a passing test suite and lethal on a
    long-lived server, which is why it is asserted rather than trusted.
    """
    from app.assembly.converter import LibreOfficeListenerConverter

    baseline = _count_soffice()
    first = LibreOfficeListenerConverter()
    second = LibreOfficeListenerConverter()
    try:
        try:
            first.convert(_docx_bytes())
        except PdfConversionError as exc:
            pytest.skip(f"no LibreOffice listener available here: {exc}")
        # Two listeners at once must not collide on a shared UNO port --
        # they used to, because unoserver's --uno-port defaults to 2002 for
        # every instance regardless of --port.
        second.convert(_docx_bytes())
    finally:
        first.shutdown()
        second.shutdown()

    for _ in range(20):
        if _count_soffice() <= baseline:
            break
        time.sleep(1)
    assert _count_soffice() <= baseline, "shutdown() orphaned a LibreOffice process"


def test_the_default_listener_does_not_collide_with_a_squatter():
    """Regression: a stale listener on a fixed port used to break the next.

    How it announced itself -- and why it was hard to spot: not an
    exception, but a restart LOOP. A listener orphaned by an earlier run
    still held port 2003, the next one could not bind, the failure surfaced
    as "conversion failed" rather than "port in use", so the retry path
    restarted it, and repeated. The visible symptom was the test suite
    crawling at ~14 s per test with five listeners alive at once.

    The default now asks the kernel for a free port, so this cannot happen.
    """
    from app.assembly.converter import LibreOfficeListenerConverter

    squatter = LibreOfficeListenerConverter(port=2003)
    auto = LibreOfficeListenerConverter()  # port 0 -> kernel picks
    try:
        try:
            squatter.convert(_docx_bytes())
        except PdfConversionError as exc:
            pytest.skip(f"no LibreOffice listener available here: {exc}")

        # The squatter owns 2003; this must still come up and stay up.
        assert auto.convert(_docx_bytes())[:5] == b"%PDF-"
        assert auto._active_port != 2003
        # And it must be REUSED, not respawned, on the next call.
        port_after_first = auto._active_port
        auto.convert(_docx_bytes())
        assert auto._active_port == port_after_first, "listener was restarted, not reused"
    finally:
        auto.shutdown()
        squatter.shutdown()


def test_a_group_member_that_ignores_sigterm_is_still_killed():
    """The oosplash leak, reproduced without LibreOffice.

    LibreOffice's launcher can block SIGTERM, and the old shutdown escalated
    to SIGKILL only if the LEADER refused to die -- so a member that shrugged
    off SIGTERM outlived every shutdown. Here the leader exits politely and a
    child ignores SIGTERM outright; after the stop, the child must be gone.
    """
    import os
    import signal
    import subprocess
    import sys

    from app.assembly.converter import _group_has_live_members, _stop_process_group

    child = "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(120)"
    leader = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"import subprocess, sys, time; "
            f"subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(120)",
        ],
        start_new_session=True,
    )
    group = leader.pid
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:  # wait for the stubborn child to exist
            members = subprocess.run(
                ["ps", "-o", "pid=", "-g", str(group)], capture_output=True, text=True
            ).stdout.split()
            if len(members) >= 2:
                break
            time.sleep(0.1)
        assert _group_has_live_members(group)

        _stop_process_group(leader, group)

        assert not _group_has_live_members(group)
    finally:
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass
