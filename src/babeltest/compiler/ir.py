"""Intermediate Representation (IR) models for BabelTest.

The IR is the JSON format that adapters consume. For now, we hand-write IR
to prove the adapter layer works before building the .babel parser.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExpectationType(str, Enum):
    """Type of expectation/assertion."""

    EXACT = "exact"  # Exact value match
    CONTAINS = "contains"  # Partial object match
    TYPE = "type"  # Type name check
    NULL = "null"  # Null check
    NOT_NULL = "not_null"  # Not null check
    TRUE = "true"  # Boolean true
    FALSE = "false"  # Boolean false


class Expectation(BaseModel):
    """An assertion about the return value."""

    type: ExpectationType = ExpectationType.EXACT
    value: Any = None


class ThrowsExpectation(BaseModel):
    """An assertion that the call should raise an exception."""

    type: str | None = None  # Exception type name
    message: str | None = None  # Message substring
    code: int | str | None = None  # Error code


class MockSpec(BaseModel):
    """A mock definition for a dependency."""

    target: str  # What to mock (e.g., "PaymentGateway.charge")
    given: dict[str, Any] | str = "any"  # Input matcher ("any" or specific values)
    returns: Any | None = None  # Return value
    throws: ThrowsExpectation | None = None  # Exception to raise


class CalledAssertion(BaseModel):
    """Assertion that a method was called (spy verification)."""

    target: str  # What should have been called (e.g., "EmailService.send")
    with_args: dict[str, Any] | None = None  # Expected arguments (partial match)
    times: int | None = None  # Expected call count (None = at least once)


class MutatesSpec(BaseModel):
    """Side-effect assertions for a test."""

    called: list[CalledAssertion] = Field(default_factory=list)
    # Future: emitted, query


class TestSpec(BaseModel):
    """A single test case specification."""

    target: str  # What to test (e.g., "UserService.get_by_id")
    description: str | None = None  # Human-readable description
    given: dict[str, Any] = Field(default_factory=dict)  # Input parameters
    types: dict[str, str] = Field(default_factory=dict)  # Type hints for given params
    expect: Expectation | None = None  # Return value assertion
    throws: ThrowsExpectation | None = None  # Exception assertion
    mocks: list[MockSpec] = Field(default_factory=list)  # Mock definitions
    mutates: MutatesSpec | None = None  # Side-effect assertions
    timeout_ms: int | None = None  # Timeout in milliseconds


class SuiteSpec(BaseModel):
    """A suite of related tests."""

    name: str
    target: str | None = None  # Default target for all tests in suite
    tests: list[TestSpec] = Field(default_factory=list)


class IRDocument(BaseModel):
    """Root document for BabelTest IR."""

    version: str = "0.1"
    suites: list[SuiteSpec] = Field(default_factory=list)
    tests: list[TestSpec] = Field(default_factory=list)  # Top-level tests outside suites
