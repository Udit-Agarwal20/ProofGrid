"""Requirement Compiler package for ProofGrid."""

from app.application.requirement_compiler.errors import (
    CompilerConfigurationError,
    CompilerProviderError,
    CompilerValidationError,
    RequirementCompilerError,
)
from app.application.requirement_compiler.models import (
    Ambiguity,
    AmbiguitySeverity,
    Assumption,
    ClarificationContext,
    ClarificationQuestion,
    CompilationContext,
    CompilationOutcome,
    CompilerClarificationResult,
    CompilerMetadata,
    CompilerResult,
)
from app.application.requirement_compiler.prompts import (
    REQUIREMENT_COMPILER_PROMPT_VERSION,
    build_compiler_request,
    build_system_instruction,
)
from app.application.requirement_compiler.service import RequirementCompiler
from app.application.requirement_compiler.validation import validate_compilation_draft

__all__ = [
    "Ambiguity",
    "AmbiguitySeverity",
    "Assumption",
    "ClarificationContext",
    "ClarificationQuestion",
    "CompilationContext",
    "CompilationOutcome",
    "CompilerClarificationResult",
    "CompilerConfigurationError",
    "CompilerMetadata",
    "CompilerProviderError",
    "CompilerResult",
    "CompilerValidationError",
    "REQUIREMENT_COMPILER_PROMPT_VERSION",
    "RequirementCompiler",
    "RequirementCompilerError",
    "build_compiler_request",
    "build_system_instruction",
    "validate_compilation_draft",
]
