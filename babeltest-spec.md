# BabelTest — GraphQL for Unit Testing

## Technical Specification v0.1 (DRAFT)

---

## 1. Vision

A declarative, language-agnostic query language for defining unit tests. BabelTest separates **what is being tested** (behavior specification) from **how the code is invoked** (runtime adapter). One test definition works across any target language — C#, Python, JavaScript, Rust, Go, Java, and beyond.

Think: **GraphQL for unit testing.**

---

## 2. Problem Statement

Every language ecosystem reinvents unit testing:

| Language | Framework(s) | Syntax Style |
|----------|-------------|--------------|
| C# | xUnit, NUnit, MSTest | Attribute-decorated classes |
| Python | pytest, unittest | Functions/classes with assertions |
| JavaScript | Jest, Mocha, Vitest | describe/it blocks |
| Rust | built-in | #[test] annotated functions |
| Go | built-in | TestXxx functions |
| Java | JUnit, TestNG | Annotated methods |

They all express the same fundamental thing: **given input X, calling Y produces Z.** But each requires learning a new syntax, new assertion library, new runner, and new config. Teams with polyglot stacks end up writing the same logical tests in multiple syntaxes.

---

## 3. Core Language Design

### 3.1 Test Declaration

```babel
TEST <target> [AS "<description>"]
  GIVEN { <input_params> }
  [EXPECT <return_assertion>]
  [THROWS <error_assertion>]
  [MUTATES <side_effect_assertion>]
  [WHERE <conditional_assertions>]
  [TIMEOUT <duration>]
```

### 3.2 Targeting

Targets use a universal dot-notation path that the runtime adapter maps to the target language's actual invocation pattern:

```babel
# Class method
TEST UserService.GetById

# Static/module function
TEST utils.math.calculate_tax

# Nested namespace
TEST App.Services.Auth.ValidateToken

# Constructor
TEST UserService.NEW
```

### 3.3 Input Specification (GIVEN)

Inputs use a JSON-like syntax with optional type hints for statically typed languages:

```babel
# Simple values
GIVEN { id: 42 }

# Complex objects
GIVEN {
  user: {
    name: "Kohl",
    email: "kohl@example.com",
    roles: ["admin", "user"]
  }
}

# Typed values (for languages that need disambiguation)
GIVEN { amount: 99.95 AS decimal, count: 10 AS int }

# Empty / null / edge cases
GIVEN {}
GIVEN { input: NULL }
GIVEN { name: "" }
```

### 3.4 Return Assertions (EXPECT)

```babel
# Exact match
EXPECT { total: 25.00 }

# Partial match (only assert on specified fields)
EXPECT CONTAINS { name: "Kohl", active: true }

# Type check
EXPECT TYPE "User"

# Value check
EXPECT 42

# Boolean shorthand
EXPECT TRUE
EXPECT FALSE

# Null check
EXPECT NULL
EXPECT NOT NULL
```

### 3.5 Error Assertions (THROWS)

```babel
# By type
THROWS { type: "ValidationError" }

# By message pattern
THROWS { message: CONTAINS "not found" }

# By type and code
THROWS { type: "HttpException", code: 404 }

# Any error
THROWS ANY
```

### 3.6 Side Effect Assertions (MUTATES)

For testing methods that change state rather than return values:

```babel
# Database state after call
MUTATES {
  QUERY "Users WHERE id = 42" CONTAINS { name: "Updated Name" }
}

# Service was called
MUTATES {
  CALLED EmailService.Send WITH { to: "kohl@example.com" }
}

# Event was emitted
MUTATES {
  EMITTED "UserUpdated" WITH { userId: 42 }
}
```

### 3.7 Conditional Assertions (WHERE)

For complex post-hoc assertions on the response:

```babel
TEST OrderService.CalculateTotal AS "applies bulk discount"
  GIVEN { items: [{ price: 10, qty: 100 }] }
  EXPECT CONTAINS { discountApplied: true }
  WHERE {
    response.total < 1000,
    response.total > 0,
    response.discountPercent >= 5
  }
```

### 3.8 Comparison Operators

```
==         Equal (default for EXPECT)
!=         Not equal
>          Greater than
<          Less than
>=         Greater or equal
<=         Less or equal
CONTAINS   String/array contains value
MATCHES    Regex match
IN         Value exists in set
BETWEEN    Range check (inclusive)
```

---

## 4. Test Organization

### 4.1 Suites

```babel
SUITE "User Management" {
  TARGET UserService

  # All tests in this suite target UserService by default
  TEST .GetById AS "returns user by id"
    GIVEN { id: 42 }
    EXPECT CONTAINS { name: "Kohl" }

  TEST .GetById AS "returns null for missing user"
    GIVEN { id: 9999 }
    EXPECT NULL

  TEST .Create AS "creates new user"
    GIVEN { name: "New User", email: "new@example.com" }
    EXPECT CONTAINS { id: NOT NULL }
}
```

### 4.2 Setup and Teardown

```babel
SUITE "Order Processing" {
  BEFORE EACH {
    SEED "test_db" WITH "fixtures/orders.json"
  }

  AFTER EACH {
    CLEAN "test_db"
  }

  BEFORE ALL {
    START "mock_payment_gateway" ON PORT 9999
  }

  AFTER ALL {
    STOP "mock_payment_gateway"
  }

  TEST OrderService.Place AS "places valid order"
    GIVEN { userId: 1, items: [{ sku: "ABC", qty: 2 }] }
    EXPECT CONTAINS { status: "placed" }
}
```

### 4.3 Parameterized Tests

```babel
TEST MathUtils.Add AS "basic addition" WITH PARAMS [
  { a: 1, b: 2, expected: 3 },
  { a: -1, b: 1, expected: 0 },
  { a: 0, b: 0, expected: 0 },
  { a: 999999, b: 1, expected: 1000000 }
]
  GIVEN { a: $a, b: $b }
  EXPECT $expected
```

### 4.4 Mocking

```babel
TEST OrderService.Place AS "handles payment failure"
  MOCK PaymentGateway.Charge
    GIVEN ANY
    THROWS { type: "PaymentDeclined" }
  GIVEN { userId: 1, items: [{ sku: "ABC", qty: 1 }] }
  THROWS { type: "OrderFailedException" }
```

---

## 5. Runtime Adapter Architecture

### 5.1 Overview

BabelTest does NOT execute tests directly. It compiles to an intermediate representation (IR) that language-specific adapters consume.

```
┌──────────┐     ┌──────────┐     ┌──────────────────┐     ┌──────────┐
│ .babel   │────▸│ BabelTest│────▸│ Adapter           │────▸│ Test     │
│ files    │     │ Compiler │     │ (C#/Py/JS/etc.)   │     │ Results  │
└──────────┘     └──────────┘     └──────────────────┘     └──────────┘
                      │
                      ▼
                 ┌──────────┐
                 │ IR       │
                 │ (JSON)   │
                 └──────────┘
```

### 5.2 Intermediate Representation

The compiler outputs JSON that adapters consume:

```json
{
  "version": "0.1",
  "suites": [
    {
      "name": "User Management",
      "defaultTarget": "UserService",
      "tests": [
        {
          "target": "UserService.GetById",
          "description": "returns user by id",
          "given": { "id": 42 },
          "expect": {
            "type": "contains",
            "value": { "name": "Kohl" }
          }
        }
      ]
    }
  ]
}
```

### 5.3 Adapter Interface

Each language adapter implements:

```
AdapterInterface {
  resolve(target: string) -> InvocableReference
  invoke(ref: InvocableReference, params: object) -> Result
  assertReturn(result: Result, expectation: Expectation) -> Pass | Fail
  assertThrows(result: Result, expectation: Expectation) -> Pass | Fail
  assertMutates(result: Result, mutations: Mutation[]) -> Pass | Fail
  setup(config: SetupConfig) -> void
  teardown(config: TeardownConfig) -> void
}
```

### 5.4 Adapter Discovery

Adapters are registered via config:

```yaml
# babeltest.config.yaml
adapters:
  - language: csharp
    adapter: "@babeltest/adapter-dotnet"
    project: "./src/MyApp.csproj"

  - language: python
    adapter: "@babeltest/adapter-python"
    module: "src.myapp"

  - language: javascript
    adapter: "@babeltest/adapter-node"
    entry: "./src/index.js"
```

---

## 6. CLI Interface

```bash
# Run all tests
babel run

# Run specific suite
babel run --suite "User Management"

# Run against specific adapter
babel run --lang csharp

# Run single test file
babel run tests/users.babel

# Compile to IR only (for custom tooling)
babel compile tests/ --output ir.json

# Generate native test files (escape hatch)
babel generate --lang python --output tests/generated/

# Watch mode
babel watch

# Validate syntax without running
babel check tests/
```

---

## 7. File Conventions

```
project/
├── babeltest.config.yaml
├── tests/
│   ├── users.babel
│   ├── orders.babel
│   ├── auth.babel
│   └── fixtures/
│       ├── users.json
│       └── orders.json
└── src/
    └── (application code in any language)
```

File extension: `.babel`

---

## 8. Native Test Generation (Escape Hatch)

For teams that want to adopt BabelTest incrementally, the `generate` command outputs native test files that can run in existing CI pipelines without BabelTest installed:

```bash
babel generate --lang csharp --output tests/generated/
```

**Input** (`users.babel`):
```babel
TEST UserService.GetById AS "returns user by id"
  GIVEN { id: 42 }
  EXPECT CONTAINS { name: "Kohl" }
```

**Output** (`UserServiceTests.cs`):
```csharp
[Fact]
public void GetById_ReturnsUserById()
{
    var result = _userService.GetById(42);
    Assert.Contains("Kohl", result.Name);
}
```

This provides a zero-risk adoption path. Teams write tests in BabelTest, generate native files for their existing toolchain, and migrate to the BabelTest runner at their own pace.

---

## 9. Open Design Questions

1. **Async handling** — How should async/await patterns be expressed declaratively? Proposal: `TEST ... ASYNC` modifier with optional `TIMEOUT 5s`. The adapter handles the actual async invocation mechanics.

2. **Dependency injection** — How does BabelTest know how to construct a `UserService`? Adapters need a DI container or factory registration mechanism. This is the hardest cross-language problem in the spec.

3. **Database fixtures** — The `SEED` command needs a standard fixture format. JSON is the obvious choice, but should the spec also address schema setup and migrations?

4. **Mock depth** — The current spec supports one level of mocking. Should nested/chained mocks be supported? e.g., `MOCK ServiceA.Method WHICH CALLS ServiceB.Other`

5. **Property-based testing** — Should BabelTest support generative/fuzz testing? e.g., `GIVEN { name: ANY string(1..100) } EXPECT NOT THROWS`

6. **Coverage reporting** — Should coverage be a first-class BabelTest concern, or delegated entirely to adapters?

7. **Snapshot testing** — Should there be an `EXPECT SNAPSHOT` assertion that auto-captures output and diffs against a stored baseline? Useful for complex return objects.

8. **Performance assertions** — e.g., `EXPECT WITHIN 100ms`. Cross-language performance comparison is inherently tricky, so this may be better left to adapters.

9. **Integration vs. unit boundary** — BabelTest is designed for unit tests. Should it explicitly support integration test patterns (multi-step workflows, stateful sequences), or stay opinionated about scope?

10. **LSP / Editor support** — Language Server Protocol implementation for syntax highlighting, autocomplete, inline test results, and go-to-definition in editors.

---

## 10. Implementation Roadmap

### Phase 1: Core Language
- [ ] BabelTest parser (formal grammar definition + parser generator)
- [ ] IR compiler (BabelTest → JSON)
- [ ] CLI scaffolding (`run`, `check`, `compile`)
- [ ] First adapter (Python or JavaScript — fastest iteration cycle)

### Phase 2: Adapter Ecosystem
- [ ] Second adapter
- [ ] Third adapter (C# — immediate practical use)
- [ ] Adapter SDK (documentation + tooling for community-built adapters)
- [ ] `generate` command for native test output

### Phase 3: Developer Tooling
- [ ] Watch mode
- [ ] VS Code extension (syntax highlighting + inline results)
- [ ] CI/CD integration guides (GitHub Actions, GitLab CI, Azure DevOps)
- [ ] Fixture management utilities

### Phase 4: Advanced Features
- [ ] Parameterized tests
- [ ] Mocking system
- [ ] Property-based testing
- [ ] Coverage integration
- [ ] Snapshot testing

### Phase 5: Agent-Assisted Generation
- [ ] Source code analyzer (function signatures, types, logic paths)
- [ ] `.babel` spec generator from analysis output
- [ ] Claude Code subagent integration
- [ ] VS Code extension integration
- [ ] CI/CD hook for flagging untested code paths

---

## 11. Agent-Assisted Test Generation (Future)

### 11.1 Vision

A specialized AI subagent that analyzes source code and automatically generates `.babel` test specs. The agent doesn't need to know the target testing framework — it only needs to understand the code's behavior and express it in BabelTest syntax. The adapter layer handles everything else.

### 11.2 Workflow

```
┌──────────┐     ┌──────────────┐     ┌──────────┐     ┌──────────┐
│ Source    │────▸│ BabelTest    │────▸│ .babel   │────▸│ Human    │
│ Code     │     │ Agent        │     │ specs    │     │ Review   │
└──────────┘     └──────────────┘     └──────────┘     └──────────┘
```

1. Point the agent at a module or directory
2. Agent analyzes function signatures, types, return values, and logic paths
3. Agent generates `.babel` files covering happy path, edge cases, and error cases
4. Engineer reviews and tweaks the specs in plain readable syntax
5. `babel run`

Unit testing is reduced to **code review** — you're not writing tests, you're reviewing test specs that an agent proposed, in a syntax readable enough that a non-engineer could follow along.

### 11.3 Agent Responsibilities

The agent should generate tests at three levels of coverage:

**Happy path** — does each function work with expected input?
```babel
TEST UserService.GetById AS "returns existing user"
  GIVEN { id: 1 }
  EXPECT CONTAINS { id: 1, name: NOT NULL }
```

**Edge cases** — boundary values, empty inputs, nulls
```babel
TEST UserService.GetById AS "handles zero id"
  GIVEN { id: 0 }
  EXPECT NULL

TEST UserService.GetById AS "handles negative id"
  GIVEN { id: -1 }
  THROWS { type: "ArgumentException" }
```

**Error paths** — invalid input, missing dependencies, expected failures
```babel
TEST UserService.GetById AS "throws on null id"
  GIVEN { id: NULL }
  THROWS { type: "ValidationError" }
```

### 11.4 Integration Target

Claude Code is the natural first integration point — it already has filesystem access and codebase understanding built in. A BabelTest subagent would operate as a specialized mode: "crawl this directory, identify testable units, generate specs."

Other potential integration points include VS Code extensions, GitHub Actions (generate specs on PR), and CI pipelines that flag untested code paths.

### 11.5 Why This Matters for AI

Current LLM-generated tests are tightly coupled to specific frameworks — the model needs to know "are we in Jest? pytest? xUnit?" and generates framework-specific code that may or may not match the project's conventions. BabelTest gives the AI a single, clean, universal output target. The model generates one spec; the adapter handles the rest. This dramatically simplifies AI-assisted test generation across any codebase.

---

## 12. Why This Matters

Unit testing is one of the most universally practiced and universally reinvented wheels in software engineering. Every team, every language, every framework rebuilds the same conceptual structure with different syntax. BabelTest doesn't replace existing test frameworks — it sits above them as a universal specification layer.

**Core value propositions:**

- **Polyglot teams** write tests once, run them against any implementation language
- **Non-engineers** (QA, product managers) can read and even author test specs
- **Language migration** preserves the entire test suite — only the adapter changes
- **AI code generation** gets a single, clean target for producing tests regardless of implementation language
- **Onboarding** — learn one test syntax, work in any stack on day one

The AI angle deserves emphasis. LLMs generating unit tests currently need to know the specific framework for each target language. BabelTest means the model generates one spec and the adapter handles the rest — dramatically simplifying AI-assisted test generation across any codebase.

---

*Spec version: 0.1-draft*
*Author: Kohl*
*Date: 2026-02-03*
*Status: Initial specification for development*
