"""Exceptions for the Rossmann integration."""

from __future__ import annotations


class RossmannError(Exception):
    """Base Rossmann error."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class RossmannAuthError(RossmannError):
    """Authentication failed."""


class RossmannCannotConnect(RossmannError):
    """Connection to Rossmann failed."""


class RossmannInvalidResponse(RossmannError):
    """Rossmann returned an unexpected response."""
