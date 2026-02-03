"""BabelTest parser - transforms .babel files into IR.

Uses lark for parsing and transforms the parse tree into Pydantic IR models.
"""

from pathlib import Path
from typing import Any

from lark import Lark, Transformer, v_args

from .ir import (
    CalledAssertion,
    ExpectationType,
    Expectation,
    IRDocument,
    MockSpec,
    MutatesSpec,
    SuiteSpec,
    TestSpec,
    ThrowsExpectation,
)

# Load grammar from file adjacent to this module
GRAMMAR_PATH = Path(__file__).parent / "grammar.lark"


class BabelTransformer(Transformer[Any, Any]):
    """Transform lark parse tree into BabelTest IR models."""

    # =========================================================================
    # Document structure
    # =========================================================================

    def start(self, items: list[Any]) -> IRDocument:
        """Root document - collect tests and suites."""
        suites: list[SuiteSpec] = []
        tests: list[TestSpec] = []

        for item in items:
            if item is None:
                continue
            if isinstance(item, SuiteSpec):
                suites.append(item)
            elif isinstance(item, TestSpec):
                tests.append(item)

        return IRDocument(suites=suites, tests=tests)

    # =========================================================================
    # Suite
    # =========================================================================

    def suite(self, items: list[Any]) -> SuiteSpec:
        """SUITE "name" { ... }"""
        name = items[0]  # STRING already processed
        body = items[1]  # suite_body result

        suite = SuiteSpec(name=name)

        for item in body:
            if item is None:
                continue
            if isinstance(item, str) and item.startswith("TARGET:"):
                suite.target = item[7:]  # Remove "TARGET:" prefix
            elif isinstance(item, TestSpec):
                test: TestSpec = item
                # If test target starts with ".", prepend suite target
                if suite.target and test.target.startswith("."):
                    test = TestSpec(
                        target=suite.target + test.target,
                        description=test.description,
                        given=test.given,
                        types=test.types,
                        expect=test.expect,
                        throws=test.throws,
                        mocks=test.mocks,
                        timeout_ms=test.timeout_ms,
                    )
                suite.tests.append(test)

        return suite

    def suite_item(self, items: list[Any]) -> Any:
        """Unwrap single suite item."""
        return items[0] if items else None

    def suite_body(self, items: list[Any]) -> list[Any]:
        """Collect suite items."""
        return [item for item in items if item is not None]

    def target_decl(self, items: list[Any]) -> str:
        """TARGET ClassName - returns marker string."""
        return f"TARGET:{items[0]}"

    def before_each(self, _items: list[Any]) -> None:
        """BEFORE EACH { ... } - not yet implemented."""
        return None

    def after_each(self, _items: list[Any]) -> None:
        """AFTER EACH { ... } - not yet implemented."""
        return None

    def before_all(self, _items: list[Any]) -> None:
        """BEFORE ALL { ... } - not yet implemented."""
        return None

    def after_all(self, _items: list[Any]) -> None:
        """AFTER ALL { ... } - not yet implemented."""
        return None

    # =========================================================================
    # Test
    # =========================================================================

    def test(self, items: list[Any]) -> TestSpec:
        """TEST target AS "description" ..."""
        target = items[0]
        description: str | None = None
        given: dict[str, Any] = {}
        types: dict[str, str] = {}
        expect: Expectation | None = None
        throws: ThrowsExpectation | None = None
        mocks: list[MockSpec] = []
        mutates: MutatesSpec | None = None
        timeout_ms: int | None = None

        # Flatten items - test_body is the last item and is a list
        flat_items: list[Any] = []
        for item in items[1:]:
            if isinstance(item, list):
                flat_items.extend(item)
            else:
                flat_items.append(item)

        for item in flat_items:
            if item is None:
                continue
            if isinstance(item, str) and item.startswith("AS:"):
                description = item[3:]
            elif isinstance(item, dict) and "__given__" in item:
                given = item["__given__"]
                # Extract type hints if present
                if "__types__" in item:
                    types = item["__types__"]
            elif isinstance(item, Expectation):
                expect = item
            elif isinstance(item, ThrowsExpectation):
                throws = item
            elif isinstance(item, MockSpec):
                mocks.append(item)
            elif isinstance(item, MutatesSpec):
                mutates = item
            elif isinstance(item, int) and timeout_ms is None:
                timeout_ms = item

        return TestSpec(
            target=target,
            description=description,
            given=given,
            types=types,
            expect=expect,
            throws=throws,
            mocks=mocks,
            mutates=mutates,
            timeout_ms=timeout_ms,
        )

    def target(self, items: list[Any]) -> str:
        """Test target."""
        return items[0]

    def as_clause(self, items: list[Any]) -> str:
        """AS "description" - returns marker string."""
        return f"AS:{items[0]}"

    def with_params(self, items: list[Any]) -> list[dict[str, Any]]:
        """WITH PARAMS [...] - parameterized tests (future)."""
        return items[0]

    def test_clause(self, items: list[Any]) -> Any:
        """Unwrap single test clause."""
        return items[0] if items else None

    def test_body(self, items: list[Any]) -> list[Any]:
        """Collect test clauses - flatten nested lists."""
        result: list[Any] = []
        for item in items:
            if isinstance(item, list):
                result.extend(item)
            else:
                result.append(item)
        return result

    # =========================================================================
    # GIVEN clause
    # =========================================================================

    def given_clause(self, items: list[Any]) -> dict[str, Any]:
        """GIVEN { ... } - mark with special key, extract types if present."""
        obj = items[0]

        # Check if object has type hints
        if isinstance(obj, dict) and "__values__" in obj:
            return {
                "__given__": obj["__values__"],
                "__types__": obj["__types__"],
            }

        return {"__given__": obj}

    # =========================================================================
    # EXPECT clause
    # =========================================================================

    def expect_clause(self, items: list[Any]) -> Expectation:
        """EXPECT ... - pass through expectation."""
        return items[0]

    def expect_contains(self, items: list[Any]) -> Expectation:
        """EXPECT CONTAINS { ... }"""
        return Expectation(type=ExpectationType.CONTAINS, value=items[0])

    def expect_type(self, items: list[Any]) -> Expectation:
        """EXPECT TYPE "TypeName" """
        return Expectation(type=ExpectationType.TYPE, value=items[0])

    def expect_true(self, _items: list[Any]) -> Expectation:
        """EXPECT TRUE"""
        return Expectation(type=ExpectationType.TRUE, value=True)

    def expect_false(self, _items: list[Any]) -> Expectation:
        """EXPECT FALSE"""
        return Expectation(type=ExpectationType.FALSE, value=False)

    def expect_null(self, _items: list[Any]) -> Expectation:
        """EXPECT NULL"""
        return Expectation(type=ExpectationType.NULL, value=None)

    def expect_not_null(self, _items: list[Any]) -> Expectation:
        """EXPECT NOT NULL"""
        return Expectation(type=ExpectationType.NOT_NULL, value=None)

    def expect_exact(self, items: list[Any]) -> Expectation:
        """EXPECT <value> (exact match)"""
        return Expectation(type=ExpectationType.EXACT, value=items[0])

    # =========================================================================
    # THROWS clause
    # =========================================================================

    def throws_clause(self, items: list[Any]) -> ThrowsExpectation:
        """THROWS ... - pass through."""
        return items[0]

    def throws_any(self, _items: list[Any]) -> ThrowsExpectation:
        """THROWS ANY"""
        return ThrowsExpectation()

    def throws_object(self, items: list[Any]) -> ThrowsExpectation:
        """THROWS { type: "...", message: "..." }"""
        obj = items[0]
        return ThrowsExpectation(
            type=obj.get("type"),
            message=obj.get("message"),
            code=obj.get("code"),
        )

    # =========================================================================
    # TIMEOUT clause
    # =========================================================================

    def timeout_clause(self, items: list[Any]) -> int:
        """TIMEOUT <duration> - returns milliseconds."""
        return items[0]

    def duration(self, items: list[Any]) -> int:
        """Parse duration with optional unit."""
        value = items[0]
        unit = items[1] if len(items) > 1 else "ms"

        if unit == "s":
            return int(value * 1000)
        elif unit == "m":
            return int(value * 60 * 1000)
        else:  # ms
            return int(value)

    @v_args(inline=True)
    def time_unit(self, unit: Any) -> str:
        """Time unit (ms, s, m)."""
        return str(unit)

    @v_args(inline=True)
    def TIME_UNIT(self, token: Any) -> str:
        """Pass through time unit."""
        return str(token)

    # =========================================================================
    # MOCK clause (single-line format)
    # MOCK target [WHEN matcher] RETURNS value
    # MOCK target [WHEN matcher] THROWS spec
    # =========================================================================

    def mock_clause(self, items: list[Any]) -> MockSpec:
        """MOCK Target.Method [WHEN matcher] RETURNS/THROWS ..."""
        target = items[0]
        given: dict[str, Any] | str = "any"
        returns: Any = None
        throws: ThrowsExpectation | None = None

        for item in items[1:]:
            if item is None:
                continue
            if isinstance(item, dict) and "__mock_when__" in item:
                given = item["__mock_when__"]
            elif isinstance(item, dict) and "__mock_returns__" in item:
                returns = item["__mock_returns__"]
            elif isinstance(item, ThrowsExpectation):
                throws = item

        return MockSpec(target=target, given=given, returns=returns, throws=throws)

    def mock_when(self, items: list[Any]) -> dict[str, Any]:
        """WHEN matcher - pass through."""
        return items[0]

    def mock_when_any(self, _items: list[Any]) -> dict[str, Any]:
        """WHEN ANY"""
        return {"__mock_when__": "any"}

    def mock_when_object(self, items: list[Any]) -> dict[str, Any]:
        """WHEN { ... }"""
        return {"__mock_when__": items[0]}

    def mock_result(self, items: list[Any]) -> Any:
        """Pass through mock result (RETURNS or THROWS)."""
        return items[0]

    def mock_returns(self, items: list[Any]) -> dict[str, Any]:
        """RETURNS <value>"""
        return {"__mock_returns__": items[0]}

    def mock_throws(self, items: list[Any]) -> ThrowsExpectation:
        """THROWS ..."""
        return items[0]

    # =========================================================================
    # MUTATES clause
    # =========================================================================

    def mutates_clause(self, items: list[Any]) -> MutatesSpec:
        """MUTATES { assertions... }"""
        called: list[CalledAssertion] = []

        for item in items:
            if item is None:
                continue
            if isinstance(item, CalledAssertion):
                called.append(item)

        return MutatesSpec(called=called)

    def mutates_assertion(self, items: list[Any]) -> Any:
        """Unwrap single mutates assertion."""
        return items[0] if items else None

    def called_assertion(self, items: list[Any]) -> CalledAssertion:
        """CALLED Target.Method [WITH { args }] [TIMES n]"""
        target = items[0]
        with_args: dict[str, Any] | None = None
        times: int | None = None

        for item in items[1:]:
            if item is None:
                continue
            if isinstance(item, dict) and "__called_with__" in item:
                with_args = item["__called_with__"]
            elif isinstance(item, int):
                times = item

        return CalledAssertion(target=target, with_args=with_args, times=times)

    def called_with(self, items: list[Any]) -> dict[str, Any]:
        """WITH { args }"""
        return {"__called_with__": items[0]}

    def called_times(self, items: list[Any]) -> int:
        """TIMES n"""
        return items[0]

    # =========================================================================
    # Values (JSON-like with type hints)
    # =========================================================================

    def typed_value(self, items: list[Any]) -> dict[str, Any]:
        """value [AS type] - returns dict with value and optional type."""
        value = items[0]
        type_hint = items[1] if len(items) > 1 else None
        return {"__value__": value, "__type__": type_hint}

    def type_hint(self, items: list[Any]) -> str:
        """AS type_name - returns the type name."""
        return items[0]

    @v_args(inline=True)
    def TYPE_NAME(self, token: Any) -> str:
        """Type name terminal."""
        return str(token)

    def typed_object(self, items: list[Any]) -> dict[str, Any]:
        """{ key: typed_value, ... } - returns dict with values and types."""
        result: dict[str, Any] = {}
        types: dict[str, str] = {}

        for item in items:
            if item is not None:
                key, typed_val = item
                # Extract value and type from typed_value
                if isinstance(typed_val, dict) and "__value__" in typed_val:
                    result[key] = typed_val["__value__"]
                    if typed_val["__type__"]:
                        types[key] = typed_val["__type__"]
                else:
                    result[key] = typed_val

        # If there are type hints, wrap the result
        if types:
            return {"__values__": result, "__types__": types}
        return result

    def typed_pair(self, items: list[Any]) -> tuple[str, Any]:
        """key: typed_value"""
        return (items[0], items[1])

    def object(self, items: list[Any]) -> dict[str, Any]:
        """{ key: value, ... } - returns plain dict."""
        result: dict[str, Any] = {}
        for item in items:
            if item is not None:
                key, val = item
                result[key] = val
        return result

    def pair(self, items: list[Any]) -> tuple[str, Any]:
        """key: value"""
        return (items[0], items[1])

    def key(self, items: list[Any]) -> str:
        """Object key (NAME or STRING)."""
        return str(items[0])

    def array(self, items: list[Any]) -> list[Any]:
        """[ value, ... ]"""
        return list(items)

    def param_ref(self, items: list[Any]) -> str:
        """$param - parameter reference for parameterized tests."""
        return f"${items[0]}"

    # =========================================================================
    # Identifiers
    # =========================================================================

    def dotted_name(self, items: list[Any]) -> str:
        """Dotted name like UserService.GetById"""
        # Items alternate between DOT tokens and NAME tokens
        return "".join(str(item) for item in items)

    @v_args(inline=True)
    def DOT(self, token: Any) -> str:
        """Keep the dot."""
        return "."

    # =========================================================================
    # Terminals
    # =========================================================================

    @v_args(inline=True)
    def STRING(self, token: Any) -> str:
        """Remove quotes from string."""
        s = str(token)
        return s[1:-1]  # Remove surrounding quotes

    @v_args(inline=True)
    def NUMBER(self, token: Any) -> int | float:
        """Parse number."""
        s = str(token)
        if "." in s:
            return float(s)
        return int(s)

    @v_args(inline=True)
    def NAME(self, token: Any) -> str:
        """Pass through name."""
        return str(token)

    def true(self, _items: list[Any]) -> bool:
        """Literal true."""
        return True

    def false(self, _items: list[Any]) -> bool:
        """Literal false."""
        return False

    def null(self, _items: list[Any]) -> None:
        """Literal NULL."""
        return None

    def NEWLINE(self, _token: Any) -> None:
        """Ignore newlines in results."""
        return None


class BabelParser:
    """Parser for .babel files."""

    def __init__(self) -> None:
        """Initialize the parser with the grammar."""
        self._parser = Lark(
            GRAMMAR_PATH.read_text(),
            parser="lalr",
            transformer=BabelTransformer(),
        )

    def parse(self, text: str) -> IRDocument:
        """Parse .babel source text into an IR document."""
        return self._parser.parse(text)  # type: ignore[return-value]

    def parse_file(self, path: Path | str) -> IRDocument:
        """Parse a .babel file into an IR document."""
        path = Path(path)
        return self.parse(path.read_text())


# Module-level parser instance for convenience
_parser: BabelParser | None = None


def get_parser() -> BabelParser:
    """Get or create the module-level parser instance."""
    global _parser
    if _parser is None:
        _parser = BabelParser()
    return _parser


def parse(text: str) -> IRDocument:
    """Parse .babel source text into an IR document."""
    return get_parser().parse(text)


def parse_file(path: Path | str) -> IRDocument:
    """Parse a .babel file into an IR document."""
    return get_parser().parse_file(path)
