"""Errors raised by inference adapters and understood by recovery policy."""

from typing import Any, Optional


class InvalidInferenceOutputError(RuntimeError):
    """Raised when a runtime returns unusable model outputs after successful load."""

    def __init__(
        self,
        *,
        backend: str,
        provider: str,
        detail: str,
        diagnostics: Optional[dict[str, Any]] = None,
    ):
        self.backend = str(backend)
        self.provider = str(provider)
        self.detail = str(detail)
        self.diagnostics = dict(diagnostics or {})
        super().__init__(f"{self.backend}:{self.provider}: {self.detail}")
