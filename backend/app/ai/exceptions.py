"""Exceptions for AI providers and structured generation abstraction."""


class AIProviderError(Exception):
    """Base exception for all AI provider failures."""


class AIProviderTimeoutError(AIProviderError):
    """Raised when an AI provider invocation exceeds its configured timeout."""


class AIProviderMalformedOutputError(AIProviderError):
    """Raised when provider output cannot be parsed into the expected candidate schema."""


class AIProviderConfigurationError(AIProviderError):
    """Raised when provider configuration or environment settings are invalid."""
