# BabelTest

A declarative, language-agnostic test specification language. Write tests once, run them against Python, JavaScript, and C#.

## What is BabelTest?

BabelTest is "GraphQL for unit testing" - a single `.babel` file describes your test cases in a language-neutral format, and adapters execute those tests against your actual code in any supported language.

## Quick Example

```babel
SUITE "UserService" {
  TARGET example.services.UserService

  TEST .get_by_id AS "returns user for valid ID"
    GIVEN { id: 1 }
    EXPECT CONTAINS { name: "Alice", email: "alice@example.com" }

  TEST .get_by_id AS "returns null for invalid ID"
    GIVEN { id: 999 }
    EXPECT NULL
}
```

## Syntax

### Test Structure

```babel
TEST target.path.ClassName.method AS "description"
    GIVEN { param1: value1, param2: value2 }
    EXPECT <expectation>
```

### Expectations

| Syntax | Description |
|--------|-------------|
| `EXPECT value` | Exact match |
| `EXPECT CONTAINS { key: value }` | Partial object match |
| `EXPECT TYPE "TypeName"` | Type check |
| `EXPECT TRUE` / `FALSE` | Boolean check |
| `EXPECT NULL` / `NOT NULL` | Null check |
| `THROWS { type: "Error" }` | Exception check |

### Type Hints

Use `AS` to specify type coercion for precise values:

```babel
GIVEN { amount: 99.95 AS decimal, created_at: "2024-01-15" AS date }
```

Supported types: `int`, `float`, `decimal`, `string`, `bool`, `datetime`, `date`, `time`, `uuid`

### Mocking

```babel
TEST OrderService.place_order AS "handles payment failure"
    MOCK PaymentGateway.charge WHEN ANY THROWS { type: "PaymentDeclined" }
    GIVEN { user_id: 1, amount: 99.99 }
    EXPECT CONTAINS { status: "declined" }
```

### Suites

Group related tests with shared configuration:

```babel
SUITE "Calculator Tests" {
  TARGET math.Calculator

  TEST .add AS "adds two numbers"
    GIVEN { a: 2, b: 3 }
    EXPECT 5

  TEST .divide AS "throws on division by zero"
    GIVEN { a: 10, b: 0 }
    THROWS { type: "ZeroDivisionError" }
}
```

## Supported Languages

| Language | Adapter | Status |
|----------|---------|--------|
| Python | `PythonAdapter` | Full support |
| JavaScript/Node.js | `JavaScriptAdapter` | Full support |
| C#/.NET | `CSharpAdapter` | Full support |

## Installation

```bash
pip install babeltest
```

## Usage

```bash
# Run tests
babeltest run tests/

# Run with specific adapter
babeltest run tests/ --adapter python

# Debug mode
babeltest run tests/ --debug
```

## Configuration

Create `babeltest.yaml` in your project root:

```yaml
adapters:
  python:
    source_paths:
      - src
    factories: babel/factories

  javascript:
    source_paths:
      - src
    module_type: esm

  csharp:
    project_path: src/MyProject/MyProject.csproj
```

## Factory Functions

For classes that require constructor arguments, create factory functions:

```python
# babel/factories/services.py
def user_service():
    db = create_test_database()
    return UserService(db)
```

## License

MIT
