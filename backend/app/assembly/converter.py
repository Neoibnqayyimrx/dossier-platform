"""DOCX -> PDF transport: how we reach LibreOffice, not how we render (P1a).

`app.assembly.pdf` owns the *contract* (deterministic, bookmarked,
normalized PDFs). This module owns only the question of how the bytes get
converted, because that turned out to be where all the time went.

WHY this module exists at all -- the measurement, not a guess:

    convert a 1-paragraph .docx       1109 ms
    convert a 400-paragraph .docx     1134 ms
    convert a real 3.2.P.1 section    1109 ms

399 extra paragraphs cost 25 ms. So ~1.1 s of every conversion -- about
98% of it -- was fixed cost paid before any page was laid out: forking
`soffice`, building a throwaway user profile, registering import/export
filters, bootstrapping UNO. The platform converts one document per leaf and a NAFDAC package has
dozens, so the build -- and the test suite, which rebuilds constantly --
was spending nearly all its time starting LibreOffice over and over.

Note the first attempt at this measurement was WRONG and worth recording:
timing `soffice --version` suggested startup was only ~107 ms (8% of a
call), which would have killed this phase. `--version` prints and exits
without the filter/UNO bootstrap a real conversion pays for. Converting a
trivial document through the actual code path is the honest probe -- the
fixed cost is whatever the smallest possible document costs.

The fix is not a different rendering engine (LibreOffice's DOCX fidelity is
the reason it was chosen) -- it is to start LibreOffice once and keep it.
Same measurement against a warm listener: 185 ms for the 1-paragraph
document and 206 ms for the real section -- a 6.0x improvement, ~924 ms
saved per document -- and most of what remains is spawning the small
client process rather than LibreOffice itself.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class PdfConversionError(RuntimeError):
    """Raised when a converter fails to produce a PDF.

    Defined here rather than in `pdf.py` so converters do not import their
    caller; `pdf.py` re-exports it, which is the name the rest of the
    codebase (and its tests) already use.
    """


class DocumentConverter(Protocol):
    """One method, because that is the whole job.

    Implementations return the converter's RAW pdf bytes. Determinism
    (pinned `/CreationDate`, content-derived `/ID`) is applied afterwards by
    `pdf._normalize_pdf`, and deliberately stays there: it must hold no
    matter which transport produced the file.
    """

    def convert(self, docx_bytes: bytes) -> bytes: ...

    def shutdown(self) -> None: ...


class SofficeSubprocessConverter:
    """The original behaviour: one fresh `soffice` per conversion.

    Kept, not deleted, for two reasons. It is the escape hatch when no
    listener can be started (a machine without python3-uno, say), and it is
    the reference the fidelity test compares the listener's output against
    -- "the new transport produces the same PDF as the old one" is only a
    meaningful claim if the old one is still executable.
    """

    def convert(self, docx_bytes: bytes) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docx_path = tmp_path / "input.docx"
            docx_path.write_bytes(docx_bytes)
            profile_dir = tmp_path / "lo_profile"

            try:
                result = subprocess.run(
                    [
                        "soffice",
                        "--headless",
                        "--norestore",
                        f"-env:UserInstallation=file://{profile_dir}",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        str(tmp_path),
                        str(docx_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except FileNotFoundError as exc:
                raise PdfConversionError("soffice (LibreOffice) is not installed") from exc
            except subprocess.TimeoutExpired as exc:
                raise PdfConversionError("soffice conversion timed out") from exc

            pdf_path = tmp_path / "input.pdf"
            if result.returncode != 0 or not pdf_path.exists():
                raise PdfConversionError(
                    f"soffice conversion failed (exit {result.returncode}): {result.stderr}"
                )
            return pdf_path.read_bytes()

    def shutdown(self) -> None:
        """Nothing to tear down -- every call already cleaned up after
        itself. Present so the two converters are interchangeable."""


class LibreOfficeListenerConverter:
    """One `soffice` process, started once and reused (the Phase 1a fix).

    Uses `unoserver` rather than a hand-rolled UNO bridge. WHY: the bridge
    itself is the part that is easy to get subtly wrong -- filter names,
    document closing, the `com.sun.star.*` property dance -- and unoserver
    is a maintained implementation of exactly it. The decisive point is that
    it lets the conversion client run OUT of process: our app never imports
    `uno`, so a fragile system binding (pyuno is built against the distro's
    Python, not ours) stays out of the API worker entirely, and a
    LibreOffice crash cannot take the API down with it. Recorded in
    docs/decisions/0002-document-converter.md.
    """

    def __init__(
        self,
        *,
        port: int | None = None,
        uno_python_path: str | None = None,
        start_timeout: float = 60.0,
    ) -> None:
        settings = get_settings()
        self._port = port if port is not None else settings.soffice_listener_port
        self._uno_python_path = (
            uno_python_path if uno_python_path is not None else settings.uno_python_path
        )
        self._start_timeout = start_timeout
        self._process: subprocess.Popen[bytes] | None = None
        # Resolved at start time, not here: a restart must be free to pick
        # different ports if the old ones are wedged.
        self._active_port: int | None = None
        # WHY a lock and not a pool: one UNO listener is not safely
        # reentrant -- concurrent conversions through a single bridge
        # interleave document open/close on the same office instance and
        # produce corrupt output or hangs. Conversion is ~200 ms and this
        # is not the system's bottleneck, so serializing is the honest
        # trade. It also guards start/restart against two callers racing to
        # spawn two listeners on the same port.
        self._lock = threading.RLock()

    # -- lifecycle ---------------------------------------------------------

    def _client_env(self) -> dict[str, str]:
        """`unoserver`/`unoconvert` need the distro's `uno` module, which is
        not installed in our virtualenv and cannot simply be pip-installed
        (pyuno is a compiled binding shipped with LibreOffice). Prepending
        the distro's dist-packages is how the client finds it; an empty
        setting means "it is already importable", so this stays correct on
        a system where uno is on the default path."""
        env = dict(os.environ)
        if self._uno_python_path:
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                f"{self._uno_python_path}{os.pathsep}{existing}"
                if existing
                else self._uno_python_path
            )
        return env

    @staticmethod
    def _executable(name: str) -> str:
        """unoserver's entry points live next to the running interpreter in
        a virtualenv, which is not necessarily on PATH (a systemd unit, a
        subprocess with a scrubbed environment)."""
        import sys

        candidate = Path(sys.executable).with_name(name)
        if candidate.exists():
            return str(candidate)
        found = shutil.which(name)
        if found is None:
            raise PdfConversionError(
                f"{name} not found -- install the 'unoserver' package, or set "
                f"DOCUMENT_CONVERTER=soffice-subprocess to use the slower "
                f"one-process-per-conversion path"
            )
        return found

    @staticmethod
    def _free_port() -> int:
        """Ask the kernel for a port nothing is using.

        WHY this exists: the first version used a FIXED port (2003) for the
        process-wide listener, and that is fragile in exactly the way that
        bit us. A listener orphaned by an earlier run still holds the port,
        so the next one cannot bind -- and the failure is not a clean error
        but a restart loop, with a new `soffice` piling up on every attempt.
        Observed directly: five listeners alive at once and the suite
        crawling at ~14 s per test.

        Binding to port 0 and reading back what the kernel assigned removes
        the collision entirely. There is a small race between closing this
        socket and unoserver binding it; that is the standard cost of this
        idiom and is vastly preferable to a guaranteed collision.
        """
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _resolve_port(self) -> int:
        """An explicitly configured port wins; 0 (the default) means
        'choose a free one', which is what a singleton should do."""
        return self._port if self._port else self._free_port()

    def _is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _start(self) -> None:
        """Start the listener and block until it answers, not merely until
        the process exists. WHY: `unoserver` forks `soffice` and only then
        binds its port; returning early makes the first conversion fail with
        a connection error that looks like a bug in the caller."""
        with self._lock:
            if self._is_running():
                return
            self._active_port = self._resolve_port()
            self._process = subprocess.Popen(
                [
                    self._executable("unoserver"),
                    "--port",
                    str(self._active_port),
                    # WHY --uno-port must be set explicitly, learned the
                    # hard way: --port is only the port the CLIENT talks
                    # to. unoserver starts `soffice` on its own UNO port,
                    # which defaults to 2002 for every instance. Two
                    # listeners on different --port values therefore both
                    # spawned a soffice fighting over 2002. The visible
                    # symptom was not an error but a HANG plus a pile of
                    # 20%-CPU soffice processes that never exited.
                    "--uno-port",
                    str(self._active_port + 1),
                    "--interface",
                    "127.0.0.1",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._client_env(),
                # WHY its own process group: unoserver FORKS soffice, and
                # terminating only the parent orphans a LibreOffice that
                # keeps its ports and burns CPU forever. Killing the group
                # is the only way to be sure the child goes too.
                start_new_session=True,
            )
            # WHY the try/except wraps the whole wait: anything that escapes
            # here leaves `self._process` set and running, and the next call
            # sees `_is_running()` and never restarts it. That is precisely
            # how the orphan pile-up happened.
            try:
                deadline = time.monotonic() + self._start_timeout
                while time.monotonic() < deadline:
                    if self._process.poll() is not None:
                        raise PdfConversionError(
                            f"unoserver exited immediately (code {self._process.returncode})"
                            f" -- is LibreOffice installed and python3-uno available?"
                        )
                    if self._responds():
                        return
                    time.sleep(0.25)
                raise PdfConversionError(
                    f"unoserver did not accept connections on port {self._active_port} "
                    f"within {self._start_timeout:.0f}s"
                )
            except BaseException:
                self.shutdown()
                raise

    def _responds(self) -> bool:
        """Never raise: a probe that throws would escape `_start` and leave
        a half-started listener behind -- which is how orphans accumulate."""
        try:
            probe = subprocess.run(
                [self._executable("unoping"), "--port", str(self._active_port)],
                capture_output=True,
                env=self._client_env(),
                timeout=30,
            )
        except (subprocess.TimeoutExpired, OSError):
            return False
        return probe.returncode == 0

    def shutdown(self) -> None:
        """Stop the listener AND the `soffice` it forked.

        Terminating just the parent leaves an orphaned LibreOffice holding
        its UNO port and burning CPU indefinitely -- observed directly:
        six of them, at ~20% CPU each, after a test run that had called
        shutdown() every time. Signal the whole process group instead.
        """
        with self._lock:
            if self._process is None:
                return
            try:
                group = os.getpgid(self._process.pid)
            except (ProcessLookupError, PermissionError):
                group = None

            def _signal(sig: int) -> None:
                if group is not None:
                    try:
                        os.killpg(group, sig)
                        return
                    except (ProcessLookupError, PermissionError):
                        pass
                try:
                    self._process.send_signal(sig) if self._process else None
                except ProcessLookupError:
                    pass

            self._active_port = None
            _signal(signal.SIGTERM)
            try:
                self._process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                _signal(signal.SIGKILL)
                try:
                    self._process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            self._process = None

    # -- conversion --------------------------------------------------------

    def convert(self, docx_bytes: bytes) -> bytes:
        with self._lock:
            if not self._is_running():
                self._start()
            try:
                return self._convert_once(docx_bytes)
            except PdfConversionError:
                # WHY retry exactly once, after a full restart: a listener
                # that has crashed or wedged fails EVERY subsequent call, so
                # without this one bad conversion silently poisons the rest
                # of the process's life. Restarting costs the ~1.3 s we just
                # spent this phase removing, which is why it is a recovery
                # path and not the normal one -- and why we do not loop: if
                # a fresh listener also fails, the document is the problem,
                # not the transport.
                self.shutdown()
                self._start()
                return self._convert_once(docx_bytes)

    def _convert_once(self, docx_bytes: bytes) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docx_path = tmp_path / "input.docx"
            pdf_path = tmp_path / "output.pdf"
            docx_path.write_bytes(docx_bytes)

            try:
                result = subprocess.run(
                    [
                        self._executable("unoconvert"),
                        "--port",
                        str(self._active_port),
                        "--convert-to",
                        "pdf",
                        str(docx_path),
                        str(pdf_path),
                    ],
                    capture_output=True,
                    env=self._client_env(),
                    timeout=180,
                )
            except subprocess.TimeoutExpired as exc:
                raise PdfConversionError("unoconvert timed out") from exc

            if result.returncode != 0 or not pdf_path.exists():
                raise PdfConversionError(
                    f"unoconvert failed (exit {result.returncode}): "
                    f"{result.stderr.decode('utf-8', 'replace')[:500]}"
                )
            return pdf_path.read_bytes()


class GotenbergConverter:
    """Convert over HTTP against a Gotenberg container.

    Gotenberg wraps the same LibreOffice engine behind a stateless HTTP API
    and keeps it warm itself. It exists here as a real, exercised option --
    not a paragraph in a README -- because it is the answer when LibreOffice
    should not live inside the API container at all (separate scaling, a
    read-only app image, a managed conversion service).

    Not the default: it requires a running container, and the listener gets
    the same win with no extra infrastructure.
    """

    def __init__(self, base_url: str | None = None, timeout: float = 180.0) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.gotenberg_url).rstrip("/")
        self._timeout = timeout

    def convert(self, docx_bytes: bytes) -> bytes:
        import httpx

        url = f"{self._base_url}/forms/libreoffice/convert"
        try:
            response = httpx.post(
                url,
                files={
                    # The filename matters: Gotenberg picks its conversion
                    # route from the extension, not from the content type.
                    "files": ("input.docx", docx_bytes, _DOCX_CONTENT_TYPE),
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise PdfConversionError(f"Gotenberg unreachable at {url}: {exc}") from exc

        if response.status_code != 200:
            raise PdfConversionError(
                f"Gotenberg conversion failed (HTTP {response.status_code}): "
                f"{response.text[:500]}"
            )
        return response.content

    def shutdown(self) -> None:
        """The container's lifecycle is not ours to manage."""


_DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_CONVERTERS: dict[str, type] = {
    "libreoffice-listener": LibreOfficeListenerConverter,
    "soffice-subprocess": SofficeSubprocessConverter,
    "gotenberg": GotenbergConverter,
}

_converter: DocumentConverter | None = None
_converter_lock = threading.Lock()


def get_converter() -> DocumentConverter:
    """The process-wide converter, built on first use.

    WHY lazy rather than a FastAPI startup hook: this codebase has no
    lifespan handler, and every other long-lived resource (`get_settings`,
    `get_storage_client`, the embedding client) is a lazily-built cached
    singleton. Following that keeps the CLI, the test suite and the scripts
    working without an app context -- and it means a deployment that never
    converts a document never starts LibreOffice at all.
    """
    global _converter
    with _converter_lock:
        if _converter is None:
            name = get_settings().document_converter
            try:
                factory = _CONVERTERS[name]
            except KeyError:
                raise PdfConversionError(
                    f"Unknown document_converter {name!r}; expected one of "
                    f"{', '.join(sorted(_CONVERTERS))}"
                ) from None
            _converter = factory()
        return _converter


def reset_converter() -> None:
    """Drop the process-wide converter, shutting down anything it started.

    For tests that switch converters, and for the session-scoped fixture
    that stops the listener at the end of a run so no `soffice` is left
    behind.
    """
    global _converter
    with _converter_lock:
        if _converter is not None:
            _converter.shutdown()
            _converter = None
