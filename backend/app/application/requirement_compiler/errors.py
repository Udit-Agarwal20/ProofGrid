"""Exception hierarchy for Requirement Compiler operations.

All exceptions sanitize output to prevent leakage of credentials, hidden prompts, or API keys.
"""

from __future__ import annotations


class RequirementCompilerError(Exception):
    """Base exception for all requirement compilation failures."""


class CompilerValidationError(RequirementCompilerError):
    """Raised when candidate compiler output fails deterministic validation checks."""


class CompilerProviderError(RequirementCompilerError):
    """Raised when an AI provider fails, times out, or returns unparseable content."""


class CompilerConfigurationError(RequirementCompilerError):
    """Raised when compiler or fixture configuration is invalid."""
