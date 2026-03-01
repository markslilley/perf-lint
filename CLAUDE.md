# perf-lint — Developer Guide

This file documents the architecture, conventions, and everything you need to add rules, parsers, or features. Read this before making changes.

---

## Contents

- [Project overview](#project-overview)
- [Repository layout](#repository-layout)
- [Architecture](#architecture)
  - [Data flow](#data-flow)
  - [Intermediate Representation (IR)](#intermediate-representation-ir)
  - [Parsers](#parsers)
  - [Rules and the registry](#rules-and-the-registry)
  - [Engine](#engine)
  - [Fixer](#fixer)
  - [Reporters](#reporters)
- [How to add a rule](#how-to-add-a-rule)
- [How to add an auto-fix](#how-to-add-an-auto-fix)
- [How to add a new framework](#how-to-add-a-new-framework)
- [Testing conventions](#testing-conventions)
- [Security model](#security-model)
- [Key design decisions](#key-design-decisions)
- [Commands](#commands)

---

## Project overview

perf-lint statically analyses performance test scripts (JMeter `.jmx`, k6 `.js`/`.ts`, Gatling `.scala`/`.kt`) and reports quality violations: missing think times, hardcoded values, absent assertions, unrealistic ramp patterns, and more.

**18 free rules** across three frameworks (35 Pro/Team rules live in `perf-lint-pro`). **12 rules** have safe auto-fix implementations. Every file receives a **quality score** (0–100, A–F) based on its violations.

---

## Repository layout

```
perf-lint/
├── src/perf_lint/
│   ├── __init__.py            # Version string
│   ├── cli.py                 # Click CLI — check / rules / init commands
│   ├── engine.py              # LintEngine, FileResult, LintResult
│   ├── fixer.py               # Auto-fix orchestration
│   ├── xml_utils.py           # Shared lxml secure parser (_SECURE_PARSER)
│   ├── config/
│   │   ├── loader.py          # Finds and loads .perf-lint.yml
│   │   └── schema.py          # Pydantic config schema (PerfLintConfig)
│   ├── ir/
│   │   └── models.py          # ScriptIR, Violation, Location, Severity,
│   │                          # Framework, TypedDicts for parsed_data
│   ├── parsers/
│   │   ├── base.py            # BaseParser, detect_parser()
│   │   ├── jmeter.py          # JMeterParser → JMeterParsedData
│   │   ├── k6.py              # K6Parser → K6ParsedData
│   │   └── gatling.py         # GatlingParser → GatlingParsedData
│   ├── plugins/
│   │   └── loader.py          # Loads custom rule files from config
│   ├── reporters/
│   │   ├── base.py            # BaseReporter
│   │   ├── text.py            # Rich coloured output + score badges
│   │   ├── json_reporter.py   # JSON output (mirrors to_dict())
│   │   └── sarif.py           # SARIF 2.1.0 output
│   └── rules/
│       ├── base.py            # BaseRule + RuleRegistry
│       ├── jmeter/rules.py    # JMX001–JMX025
│       ├── k6/rules.py        # K6001–K6015
│       └── gatling/rules.py   # GAT001–GAT013
├── tests/
│   ├── conftest.py            # Shared fixtures (fixture dir paths)
│   ├── fixtures/              # Minimal test scripts per framework
│   │   ├── jmeter/
│   │   ├── k6/
│   │   └── gatling/
│   ├── integration/
│   │   ├── test_cli.py        # Full CLI via Click's CliRunner
│   │   └── test_full_pipeline.py
│   ├── unit/
│   │   ├── rules/
│   │   │   ├── test_jmeter_rules.py
│   │   │   ├── test_k6_rules.py
│   │   │   └── test_gatling_rules.py
│   │   ├── test_engine.py
│   │   ├── test_fixer.py
│   │   ├── test_parsers.py     # Edge cases: empty, large, malformed
│   │   ├── test_jmeter_parser.py
│   │   ├── test_k6_parser.py
│   │   ├── test_gatling_parser.py
│   │   ├── test_ir_models.py
│   │   └── test_config_loader.py
│   └── plugins/
│       └── test_plugin_loader.py
├── samples/                   # Real-world good/bad example scripts
│   ├── jmeter/
│   ├── k6/
│   └── gatling/
├── pyproject.toml
├── README.md
└── CLAUDE.md                  # ← you are here
```

---

## Architecture

### Data flow

```
CLI (cli.py)
  │
  ├── load_config()          reads .perf-lint.yml
  ├── load_plugins()         imports custom rule files
  │
  └── LintEngine.lint_paths()
        │
        ├── detect_parser()  matches file extension → parser class
        ├── parser.parse()   → ScriptIR (raw_content + parsed_data)
        │
        ├── For each rule in RuleRegistry:
        │     rule.check(ir) → list[Violation]
        │
        ├── _apply_config_overrides()  severity/enabled per-rule config
        ├── _compute_score()           quality score (0-100) + grade
        │
        └── FileResult / LintResult

  (Optional fix pass)
  └── fixer.apply_fixes(ir, violations, rules)
        │
        ├── For each fixable violation:
        │     rule.apply_fix(ir) → new_source | None
        │     ir.raw_content = new_source  (sequential, each fix sees previous)
        │
        └── write_fixed_source(path, source)  [--fix only]

  Reporter.report(result) → text | JSON | SARIF
```

### Intermediate Representation (IR)

`ScriptIR` (`src/perf_lint/ir/models.py`) is the only data structure rules ever touch:

```python
@dataclass
class ScriptIR:
    framework: Framework        # JMETER | K6 | GATLING
    source_path: Path
    raw_content: str            # mutable — fixer updates it between passes
    parsed_data: dict[str, object]  # pre-extracted, framework-specific
```

`parsed_data` conforms to one of three TypedDicts (`JMeterParsedData`, `K6ParsedData`, `GatlingParsedData`). **Rules must read from `parsed_data` rather than re-scanning `raw_content`**, both for performance and to ensure a single point of truth for what was extracted.

`raw_content` is intentionally mutable. The fixer updates it between sequential fix passes so each rule's `apply_fix()` sees the source after all previous fixes have been applied.

### Parsers

Each parser (`src/perf_lint/parsers/*.py`) implements `BaseParser`:

```python
class BaseParser(ABC):
    supported_extensions: ClassVar[frozenset[str]]

    @abstractmethod
    def parse(self, path: Path) -> ScriptIR: ...
```

The parser is responsible for extracting **all** data from the source file that any rule might need and storing it in `parsed_data`. This happens once per file, not once per rule.

**JMeter parser** (`jmeter.py`):
- Uses `lxml` with `_SECURE_PARSER` from `xml_utils.py` (XXE-safe).
- Single-pass `for elem in root.iter()` loop — previously 4+ `findall(".//*")` calls.
- Tag matching uses module-level `frozenset` constants (`_CONFIG_ELEMENT_TAGS`, `_LISTENER_TAGS`, etc.) rather than substring checks.
- Disabled elements (checked `enabled="false"`) are excluded from counts.

**k6 parser** (`k6.py`):
- Regex-based over raw JavaScript/TypeScript.
- Heavy patterns (`_HARDCODED_AUTH_RE`, `_TAGS_IN_HTTP_RE`) cap at 1 MB to prevent ReDoS on pathological inputs.

**Gatling parser** (`gatling.py`):
- Regex-based over Scala/Kotlin source.
- `_EXEC_WITH_CHECK_RE` uses a negative lookahead (`(?:(?!\.exec\s*\()[\s\S])*?`) to prevent matching across multiple `exec()` boundaries.

### Rules and the registry

`RuleRegistry` is a singleton class dict. Rules self-register on import via the `@RuleRegistry.register` decorator:

```python
@RuleRegistry.register
class JMX001MissingCacheManager(BaseRule):
    rule_id = "JMX001"
    name = "MissingCacheManager"
    description = "HTTP Cache Manager is missing..."
    severity = Severity.WARNING
    frameworks = [Framework.JMETER]
    tags = ("configuration", "caching")
    fixable = False  # set True when apply_fix() is implemented

    def check(self, ir: ScriptIR) -> list[Violation]:
        if not ir.parsed_data.get("has_cache_manager"):
            return [Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                message="HTTP Cache Manager is missing...",
                location=Location(element_path="//ThreadGroup"),
                suggestion="Add an HTTP Cache Manager to the Thread Group.",
                fix_example='<CacheManager testname="HTTP Cache Manager" .../>',
            )]
        return []
```

`BaseRule.check()` must be pure — no side effects, no file I/O, no mutation of `ir`.

The engine imports rule modules on startup, triggering registration:
```python
import perf_lint.rules.jmeter  # noqa: F401
import perf_lint.rules.k6      # noqa: F401
import perf_lint.rules.gatling # noqa: F401
```

The registry is injectable for testing: `LintEngine(rules={"MY001": MyRule})`.

### Engine

`LintEngine` (`engine.py`) orchestrates parsing and rule evaluation:

```python
engine = LintEngine(config=config)           # production
engine = LintEngine(rules={"MY001": MyRule}) # test isolation
result = engine.lint_paths(paths, severity_override=None, ignored_rules=[])
```

**Quality scoring formula:**
```
score = max(0, 100 − (errors × 15) − (warnings × 5) − (infos × 1))
```

| Score | Grade |
|-------|-------|
| 90–100 | A |
| 75–89 | B |
| 60–74 | C |
| 40–59 | D |
| 0–39 | F |

Parse errors count as score 0. The overall score is the unweighted average across all files.

### Fixer

`apply_fixes()` in `fixer.py` iterates violations in order, calls `rule.apply_fix(ir)` for each fixable rule (at most once per rule per file), and updates `ir.raw_content` on success so subsequent fixes see the latest source.

**All `apply_fix()` implementations must be idempotent** — calling them twice must not duplicate elements. Guard pattern:

```python
def apply_fix(self, ir: ScriptIR) -> str | None:
    root = etree.fromstring(ir.raw_content.encode(), _SECURE_PARSER)
    # Check if already fixed
    if root.find(".//CacheManager") is not None:
        return None
    # Apply fix ...
    return etree.tostring(root, encoding="unicode", xml_declaration=True)
```

Security properties of `write_fixed_source()`:
- Resolves the path before writing (prevents symlink traversal).
- Verifies the file exists before writing (rejects crafted paths).
- Validates JMX encoding declarations against `_SAFE_XML_ENCODINGS` whitelist (prevents codec injection).

### Reporters

All reporters implement `BaseReporter.report(result, **kwargs) -> str`. The text reporter also accepts `fixed_by_file` and `dry_run_diffs` keyword arguments for `--fix` and `--fix-dry-run` output.

JSON and SARIF output is derived from `FileResult.to_dict()` and `LintResult.to_dict()` — add fields there first, reporters pick them up automatically.

---

## How to add a rule

1. **Choose the right file** — `src/perf_lint/rules/jmeter/rules.py`, `k6/rules.py`, or `gatling/rules.py`.

2. **Pick an ID** — next sequential ID in the framework series (`JMX026`, `K6016`, `GAT014`).

3. **Check if the parser already extracts the data you need.** Look at the relevant TypedDict in `ir/models.py`. If the data isn't there, add extraction to the parser first (and update the TypedDict).

4. **Write the rule class:**

```python
@RuleRegistry.register
class JMX026MyNewRule(BaseRule):
    rule_id = "JMX026"
    name = "MyNewRule"
    description = "One-sentence description of what this detects and why it matters."
    severity = Severity.WARNING   # ERROR | WARNING | INFO
    frameworks = [Framework.JMETER]
    tags = ("performance",)       # optional, used for filtering
    fixable = False               # set True only when apply_fix() is implemented

    def check(self, ir: ScriptIR) -> list[Violation]:
        violations = []
        if not ir.parsed_data.get("my_new_key"):
            violations.append(Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                message="Clear, actionable message explaining the specific problem.",
                location=Location(element_path="//ThreadGroup"),
                suggestion="What the user should do to fix it.",
                fix_example="<ExampleElement/>",
            ))
        return violations
```

5. **Write a fixture** — add a minimal test file to `tests/fixtures/<framework>/` that triggers (and ideally doesn't trigger) the rule.

6. **Write tests** — add to the appropriate `tests/unit/rules/test_*_rules.py`:

```python
class TestJMX026MyNewRule:
    def test_detects_violation(self, jmeter_fixtures_dir):
        parser = JMeterParser()
        ir = parser.parse(jmeter_fixtures_dir / "my_new_fixture.jmx")
        rule = JMX026MyNewRule()
        violations = rule.check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "JMX026"
        assert violations[0].severity == Severity.WARNING

    def test_no_violation_when_present(self, jmeter_fixtures_dir):
        parser = JMeterParser()
        ir = parser.parse(jmeter_fixtures_dir / "good.jmx")
        rule = JMX026MyNewRule()
        assert rule.check(ir) == []
```

7. **Update the rule count assertion** in `tests/integration/test_cli.py`:

```python
assert len(data) >= 19  # was 18; update this comment when adding rules
```

8. **Update the rule tables** in `README.md`.

---

## How to add an auto-fix

Auto-fixes are safe to add only when the fix is:
- **Insertion-only or simple substitution** — no logic changes.
- **Idempotent** — calling `apply_fix()` twice has the same effect as calling it once.
- **Framework-appropriate** — JMeter fixes use lxml DOM manipulation; k6 fixes use regex/string operations; Gatling fixes are rare (Scala AST is complex).

Steps:

1. Set `fixable = True` on the rule class.

2. Implement `apply_fix(self, ir: ScriptIR) -> str | None`:

```python
def apply_fix(self, ir: ScriptIR) -> str | None:
    root = etree.fromstring(ir.raw_content.encode(), _SECURE_PARSER)

    # Idempotency guard — already fixed?
    if root.find(".//CacheManager") is not None:
        return None

    # Build the element
    elem = etree.Element("CacheManager", testname="HTTP Cache Manager", testclass="CacheManager")

    # Insert using the shared helper
    if not _insert_into_tg_hashtree(root, elem):
        return None

    return etree.tostring(root, encoding="unicode", xml_declaration=True)
```

3. Write idempotency tests in `tests/unit/test_fixer.py`:

```python
def test_jmx026_idempotent(self):
    rule = JMX026MyNewRule()
    ir = _make_ir("<jmeterTestPlan>...</jmeterTestPlan>", Framework.JMETER)
    first = rule.apply_fix(ir)
    assert first is not None
    ir.raw_content = first
    second = rule.apply_fix(ir)
    assert second is None  # already fixed, no-op
```

4. Write an integration test in `tests/integration/test_cli.py`:

```python
def test_fix_removes_jmx026(self, runner, jmeter_fixtures_dir, tmp_path):
    tmp_file = tmp_path / "test.jmx"
    shutil.copy(jmeter_fixtures_dir / "my_new_fixture.jmx", tmp_file)
    runner.invoke(cli, ["check", str(tmp_file), "--fix"])
    result = runner.invoke(cli, ["check", str(tmp_file), "--format", "json"])
    data = json.loads(result.output)
    rule_ids = [v["rule_id"] for v in data["files"][0]["violations"]]
    assert "JMX026" not in rule_ids
```

---

## How to add a new framework

1. **Create the parser** in `src/perf_lint/parsers/<framework>.py`:

```python
class MyFrameworkParser(BaseParser):
    supported_extensions: ClassVar[frozenset[str]] = frozenset({".myext"})

    def parse(self, path: Path) -> ScriptIR:
        content = path.read_text(encoding="utf-8", errors="replace")
        parsed_data: dict[str, object] = {
            "has_think_time": bool(re.search(r"sleep\(", content)),
            # ... extract everything any rule might need
        }
        return ScriptIR(
            framework=Framework.MYFRAMEWORK,
            source_path=path,
            raw_content=content,
            parsed_data=parsed_data,
        )
```

2. **Add the Framework enum value** to `ir/models.py` and a TypedDict documenting the parsed_data keys.

3. **Register the parser** in `parsers/base.py` alongside JMeter/k6/Gatling.

4. **Add a `MYFRAMEWORK` enum value** to `ir/models.py`:`Framework.MYFRAMEWORK = "myframework"`.

5. **Create the rules directory** `src/perf_lint/rules/myframework/` with `__init__.py` and `rules.py`.

6. **Import the rules module** in both `engine.py` and `cli.py`:
   ```python
   import perf_lint.rules.myframework  # noqa: F401
   ```

7. **Add fixtures, tests, and update the CLI `--framework` choice** in `cli.py`.

---

## Testing conventions

- **265 tests** across unit, integration, and plugin suites.
- All tests use `pytest`. Run with `pytest` (config in `pyproject.toml`).
- **Unit tests** for rules test the rule class directly against parsed fixtures — they do not go through the CLI.
- **Integration tests** use Click's `CliRunner` — they exercise the full stack including config loading, plugin loading, reporters, and fix application.
- **Fixture files** are minimal and targeted. Each fixture should trigger exactly the rules it's supposed to trigger and nothing else. `good.jmx`, `good_test.js`, `GoodSimulation.scala` must produce zero violations.
- **Do not mock `ir.parsed_data`** in rule tests — parse real fixture files. This ensures parsers and rules stay in sync.
- **Test idempotency** for every `apply_fix()` implementation — call it twice and assert the second call returns `None`.
- **Test edge cases** in `tests/unit/test_parsers.py`: empty files, comment-only files, malformed XML, unicode, large (2 MB) files.
- Keep `tests/integration/test_cli.py::TestRulesCommand::test_rules_lists_all` rule count up to date when adding rules.

---

## Security model

**XML parsing (JMeter):** All XML is parsed with `_SECURE_PARSER` from `src/perf_lint/xml_utils.py`. Never use `etree.parse()` or `etree.fromstring()` without this parser. The parser sets:
- `resolve_entities=False` — prevents XXE
- `no_network=True` — prevents SSRF via external DTDs
- `dtd_validation=False, load_dtd=False` — prevents DTD-based attacks
- `huge_tree=False` — prevents billion-laughs DoS

**Auto-fix security:**
- `write_fixed_source()` resolves paths and verifies existence before writing — prevents path traversal via crafted violation data.
- JMX encoding is validated against `_SAFE_XML_ENCODINGS` whitelist before use — prevents codec injection from crafted XML declarations.

**ReDoS:**
- k6 parser caps heavy regex patterns at 1 MB (`_scan_content = content[:1_048_576]`).
- Regex patterns are anchored or use non-backtracking constructs where possible.

**No shell execution:** The tool never spawns subprocesses or evaluates user-supplied code.

---

## Key design decisions

**Why parse-once, rule-many?**
Parsers extract all data in a single pass into `parsed_data`. This makes rules simple (dict lookups), keeps them testable in isolation, and ensures consistency — two rules checking `has_assertions` see exactly the same value.

**Why class attributes, not instance attributes, for rule metadata?**
`RuleRegistry.get_all()` returns the class, not an instance. Metadata introspection (for `perf-lint rules`, SARIF tool component data, etc.) works without constructing every rule. Rules are instantiated only during `check()` and `apply_fix()`.

**Why is `raw_content` mutable on `ScriptIR`?**
Auto-fix applies rules sequentially. Each rule's `apply_fix()` needs to see the output of the previous rule's fix. Making `raw_content` mutable avoids re-parsing between every fix.

**Why frozensets for JMeter tag matching?**
The original code used substring checks (`"Manager" in elem.tag`) which produced false positives (e.g. `DownloadManager` being counted as `CookieManager`). Explicit frozenset membership (`elem.tag in _CONFIG_ELEMENT_TAGS`) is precise and fast.

**Why a shared `xml_utils.py`?**
Both `parsers/jmeter.py` and `rules/jmeter/rules.py` need the secure parser. Centralising it prevents the security configuration from diverging between the two modules.

**Why not parse Scala AST for Gatling?**
Scala AST manipulation requires a Scala toolchain. Regex over source text is fragile but deployable with zero extra dependencies. Gatling rules document their regex limitations in comments. Gatling auto-fixes are limited to insertion of top-level configuration options where the pattern is unambiguous.

---

## Commands

```bash
# Install in dev mode
pip install -e ".[dev]"

# All tests
pytest

# Tests with coverage
pytest --cov=perf_lint --cov-report=term-missing

# Single test file
pytest tests/unit/rules/test_jmeter_rules.py -v

# Specific test
pytest tests/unit/rules/test_jmeter_rules.py::TestJMX001::test_detects_violation -v

# Lint
ruff check src/ tests/

# Type check
mypy src/

# Check the tool against its own samples
perf-lint check samples/ --no-color
perf-lint check samples/ --format json | python3 -m json.tool

# List all rules
perf-lint rules
perf-lint rules --framework jmeter --json | python3 -m json.tool

# Regenerate starter config
perf-lint init --output /tmp/test.perf-lint.yml
```
