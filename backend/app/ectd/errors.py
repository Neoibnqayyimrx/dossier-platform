"""eCTD publishing errors (gap Phase 4b).

Its own module only because both `app.ectd.backbone` and the regional
builders it dispatches to raise it, and the backbone imports those builders.
"""

from __future__ import annotations


class EctdNotSupportedError(NotImplementedError):
    """This project cannot be published as an eCTD sequence, and the message
    says why in terms the filer can act on.

    A NotImplementedError so the API's existing 422 mapping (app/api/
    routers/ectd.py) applies unchanged. Raised BEFORE assembly wherever
    possible: a refusal that arrives after two minutes of LibreOffice
    conversions is a refusal that could have been instant.
    """
