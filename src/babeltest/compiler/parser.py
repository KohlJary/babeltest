"""BabelTest parser - transforms .babel files into IR.

Uses lark for parsing and transforms the parse tree into Pydantic IR models.
"""

from pathlib import Path
from typing import Any

from lark import Lark, Transformer, v_args

from .ir import (
    ExpectationType,
    Expectation,
    IRDocument,
    MockSpec,
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
        expect: Expectation | None = None
        throws: ThrowsExpectation | None = None
        mocks: list[MockSpec] = []
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
            elif isinstance(item, Expectation):
                expect = item
            elif isinstance(item, ThrowsExpectation):
                throws = item
            elif isinstance(item, MockSpec):
                mocks.append(item)
            elif isinstance(item, int) and timeout_ms is None:
                timeout_ms = item

        return TestSpec(
            target=target,
            description=description,
            given=given,
            expect=expect,
            throws=throws,
            mocks=mocks,
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
        """GIVEN { ... } - mark with special key."""
        return {"__given__": items[0]}

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
    # MOCK clause
    # =========================================================================

    def mock_clause(self, items: list[Any]) -> MockSpec:
        """MOCK Target.Method ..."""
        target = items[0]
        given: dict[str, Any] | str = "any"
        returns: Any = None
        throws: ThrowsExpectation | None = None

        for item in items[1:]:
            if item is None:
                continue
            if isinstance(item, dict) and "__mock_given__" in item:
                given = item["__mock_given__"]
            elif isinstance(item, dict) and "__mock_returns__" in item:
                returns = item["__mock_returns__"]
            elif isinstance(item, ThrowsExpectation):
                throws = item

        return MockSpec(target=target, given=given, returns=returns, throws=throws)

    def mock_body(self, items: list[Any]) -> list[Any]:
        """Collect mock items."""
        return items

    def mock_given_any(self, _items: list[Any]) -> dict[str, Any]:
        """GIVEN ANY"""
        return {"__mock_given__": "any"}

    def mock_given_object(self, items: list[Any]) -> dict[str, Any]:
        """GIVEN { ... }"""
        return {"__mock_given__": items[0]}

    def mock_returns(self, items: list[Any]) -> dict[str, Any]:
        """RETURNS <value>"""
        return {"__mock_returns__": items[0]}

    def mock_throws(self, items: list[Any]) -> ThrowsExpectation:
        """THROWS ..."""
        return items[0]

    # =========================================================================
    # Values (JSON-like)
    # =========================================================================

    def object(self, items: list[Any]) -> dict[str, Any]:
        """{ key: value, ... }"""
        result: dict[str, Any] = {}
        for item in items:
            if item is not None:
                key, value = item
                result[key] = value
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
