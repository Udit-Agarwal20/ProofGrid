"""Exceptions for AI providers and structured generation abstraction."""


class AIProviderError(Exception):
    """Base exception for all AI provider failures."""


class AIProviderTimeoutError(AIProviderError):
    """Raised when an AI provider invocation exceeds its configured timeout."""


class AIProviderMalformedOutputError(AIProviderError):
    """Raised when provider output cannot be parsed into the expected candidate schema."""


class AIProviderConfigurationError(AIProviderError):
    """Raised when provider configuration or environment settings are invalid."""


class AIProviderRateLimitError(AIProviderError):
    """Raised when an AI provider rate limit or request quota is reached (HTTP 429)."""


class AIProviderBillingError(AIProviderError):
    """Raised when an AI provider payment, billing, or prepaid credit balance is depleted (HTTP 402)."""


class AIProviderAuthenticationError(AIProviderError):
    """Raised when an AI provider authentication or permission check fails (HTTP 401/403)."""
