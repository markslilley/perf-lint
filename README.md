# perf-lint

A static analyser for performance test scripts. Catches missing think times, hardcoded values, absent assertions, unrealistic ramp-up patterns, and 45 other quality problems before they produce misleading load test results.

Supports **JMeter** (`.jmx`), **k6** (`.js`/`.ts`), and **Gatling** (`.scala`/`.kt`).

```
$ perf-lint check tests/k6/ecommerce.js --no-color

  ecommerce.js (k6)  [D 55/100]
  ────────────────────────────────────────────────────
  E [K6002] HardcodedURL — HTTP call uses a hardcoded IP address. (line 12)
  W [K6001] MissingThinkTime — No sleep() calls found. (line 1)  [fixable]
  W [K6004] MissingThresholds — No thresholds defined in options. (line 1)  [fixable]

  Summary
  ───────────────────────────────
  Files checked      1
  Violations         3  (1 error, 2 warnings)
  Fixable            2
  Quality score      D  55/100
```

---

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Rules](#rules)
  - [JMeter (25 rules)](#jmeter-25-rules)
  - [k6 (15 rules)](#k6-15-rules)
  - [Gatling (13 rules)](#gatling-13-rules)
- [Quality scoring](#quality-scoring)
- [Auto-fix](#auto-fix)
- [CLI reference](#cli-reference)
- [Configuration](#configuration)
- [Output formats](#output-formats)
- [CI/CD integration](#cicd-integration)
- [Custom rules](#custom-rules)
- [Development](#development)

---

## Installation

```bash
pip install perf-lint
```

Requires Python 3.11+.

---

## Quick start

```bash
# Analyse a single script
perf-lint check my-test.js

# Analyse a directory (all supported file types, recursively)
perf-lint check ./performance-tests/

# Fix what can be fixed automatically, then report what remains
perf-lint check ./performance-tests/ --fix

# Preview fixes without writing anything to disk
perf-lint check ./performance-tests/ --fix-dry-run

# JSON output for CI pipelines
perf-lint check ./performance-tests/ --format json | jq .

# SARIF output for GitHub Code Scanning
perf-lint check ./performance-tests/ --format sarif --output results.sarif

# Generate a starter config
perf-lint init
```

---

## Rules

Run `perf-lint rules` to list all rules with their current configuration, or `perf-lint rules --json` for machine-readable output.

### JMeter (25 rules)

| ID | Name | Severity | Fixable | Description |
|----|------|----------|---------|-------------|
| JMX001 | MissingCacheManager | warning | yes | HTTP Cache Manager is missing. Without it, JMeter won't simulate browser caching, producing unrealistically high load. |
| JMX002 | MissingCookieManager | warning | yes | HTTP Cookie Manager is missing. Sessions won't be maintained between requests. |
| JMX003 | ConstantTimerOnly | info | no | Only Constant Timers used. Real users don't think at perfectly regular intervals — use Gaussian or Uniform random timers. |
| JMX004 | RampupTooShort | error | no | Ramp-up period is too short relative to thread count (< 0.5 seconds per thread), causing an unrealistic spike load. |
| JMX005 | MissingAssertion | error | yes | No assertions found. Without assertions, the test cannot detect application failures — passing tests mean nothing. |
| JMX006 | HardcodedHostInSampler | error | yes | Sampler uses a hardcoded IP address instead of a hostname or variable. Prevents running against different environments. |
| JMX007 | MissingCSVDataSet | info | no | Multiple samplers but no CSV Data Set. All virtual users send identical requests, producing unrealistic results. |
| JMX008 | NoVariableUsage | warning | no | Multiple samplers but no JMeter variables (`${VAR}`) used. All virtual users send identical static requests. |
| JMX009 | MissingHeaderManager | warning | yes | No HTTP Header Manager found. Requests won't simulate real browser behaviour without common headers. |
| JMX010 | NoHTTPDefaults | info | yes | No HTTP Request Defaults found. Host, port, and protocol are duplicated in every sampler. |
| JMX011 | NoDurationAssertion | info | yes | No Duration Assertion found. Slow responses will pass silently even when they breach performance objectives. |
| JMX012 | NoResultCollector | info | yes | No result listener found. The test has no persistent results when run from the GUI. |
| JMX013 | MissingTransactionController | info | no | Multiple samplers but no Transaction Controller. End-to-end response times for user journeys cannot be reported. |
| JMX014 | BeanShellUsage | warning | yes | BeanShell detected. Deprecated since JMeter 3.1 and single-threaded — serialises execution under load. Use JSR223/Groovy. |
| JMX015 | ZeroThinkTime | error | yes | ConstantTimer with delay ≤ 50 ms. Gives false confidence that think time is configured while still hammering the server. |
| JMX016 | MissingCorrelation | error | no | Request bodies contain hardcoded session tokens but no extractors configured. Hardcoded tokens fail under concurrent users. |
| JMX017 | MissingConnectionTimeout | warning | yes | HTTP Request Defaults has no connection timeout. A hung connection blocks a VU thread indefinitely. |
| JMX018 | MissingResponseTimeout | warning | yes | HTTP Request Defaults has no response timeout. Slow responses block VU threads indefinitely. |
| JMX019 | InfiniteLoop | warning | yes | Thread Group loop count is -1 (infinite) without a scheduler. This test runs forever unless manually stopped. |
| JMX020 | HardcodedPort | warning | yes | HTTP sampler uses a hardcoded non-standard port. Prevents pointing the test at different environments. |
| JMX021 | MissingContentTypeHeader | warning | yes | POST/PUT/PATCH samplers without a Content-Type header. Many frameworks reject or misparse request bodies without it. |
| JMX022 | SizeAssertionMissing | info | yes | No Size Assertion found. Truncated or stub responses (e.g. 0-byte WAF blocks) pass response-code assertions silently. |
| JMX023 | NoBackendListener | info | yes | No BackendListener found. Real-time result streaming to InfluxDB/Graphite is not configured. |
| JMX024 | MultipleThreadGroupsNoSync | info | no | Multiple Thread Groups but no SetupThreadGroup. Metrics are merged in default listeners, producing misleading aggregates. |
| JMX025 | RegexExtractorGreedyMatch | warning | yes | RegexExtractor uses a greedy pattern (`.+` or `.*`). Greedy extractors break under slightly different response sizes. |

### k6 (15 rules)

| ID | Name | Severity | Fixable | Description |
|----|------|----------|---------|-------------|
| K6001 | MissingThinkTime | warning | yes | No `sleep()` calls found. Without think time, VUs hammer the server as fast as possible. |
| K6002 | HardcodedURL | error | no | HTTP call uses a hardcoded IP address. Prevents running against different environments. |
| K6003 | MissingCheck | error | yes | No `check()` calls found. Without checks, k6 cannot detect application errors — all requests appear successful. |
| K6004 | MissingThresholds | warning | yes | No thresholds defined in options. k6 won't fail the test when SLOs are breached. |
| K6005 | MissingErrorHandling | warning | no | No error handling found. Failed requests may cause unexpected script behaviour. |
| K6006 | AggressiveStages | warning | yes | First stage ramps up > 100 users in < 10 seconds — unrealistic spike load. |
| K6007 | MissingTeardown | warning | yes | `setup()` exported but no `teardown()`. Resources created in setup (users, sessions) leak into the target system. |
| K6008 | HardcodedAuthToken | error | no | Hardcoded `Authorization` header value detected. Tokens expire mid-test causing silent 401 responses. |
| K6009 | MissingGroup | warning | no | Multiple HTTP calls but no `group()`. End-of-test summary cannot report composite response times for user journeys. |
| K6010 | MissingRequestTag | warning | yes | HTTP calls with no custom tags. Every URL variation becomes its own metric label, causing cardinality explosion. |
| K6011 | SharedArrayNotUsed | warning | no | `open()` used without `SharedArray`. Data re-allocated per VU iteration instead of shared across all VUs. |
| K6012 | MissingGracefulStop | warning | yes | stages/scenarios defined but no `gracefulStop`. VUs killed mid-request at test end inflate the final error rate. |
| K6013 | ClosedModelOnly | info | no | VU-based stages only (closed model). Under slow responses, throughput drops. Consider constant-arrival-rate for throughput SLOs. |
| K6014 | MissingConnectionTimeout | info | no | No timeout parameter on HTTP calls. Default 60 s timeout exhausts VUs quickly under a slow target. |
| K6015 | MissingCustomMetrics | info | no | Long script with many HTTP calls but no custom metrics. Only HTTP stats captured — no business outcomes. |

### Gatling (13 rules)

| ID | Name | Severity | Fixable | Description |
|----|------|----------|---------|-------------|
| GAT001 | MissingPause | warning | no | `exec()` calls found but no `pause()`. VUs hammer the server without think time. |
| GAT002 | HardcodedBaseURL | error | no | `baseUrl` uses a hardcoded IP address. Prevents running against different environments. |
| GAT003 | MissingAssertions | error | yes | No assertions found. Simulation cannot enforce SLOs or detect performance regressions. |
| GAT004 | AggressiveRampup | warning | yes | Ramp-up rate exceeds 10 users/second — unrealistic spike load. |
| GAT005 | MissingFeeder | info | no | Multiple `exec()` calls but no feeder configured. All VUs send identical requests. |
| GAT006 | MissingMaxDuration | error | yes | No `.maxDuration()` configured. A stalled simulation runs forever, blocking CI pipelines. |
| GAT007 | MissingResponseCheck | error | no | HTTP `exec()` found without `.check()`. Gatling silently passes 500s and empty bodies without it. |
| GAT008 | AtOnceUsersAggressive | warning | yes | `atOnceUsers()` > 10 — injects all VUs simultaneously with zero ramp. Use `rampUsers()` instead. |
| GAT009 | MissingConnectionTimeout | warning | yes | No `.connectionTimeout()` or `.readTimeout()`. VU threads block indefinitely on slow targets. |
| GAT010 | MissingSessionCorrelation | warning | no | Multiple requests but no `.saveAs()` extraction. Static recorded values fail under concurrent users (401/403). |
| GAT011 | AssertionLacksThreshold | info | no | Assertions present but none reference `responseTime` or `failedRequests`. No meaningful SLO enforced. |
| GAT012 | HardcodedPauseDuration | info | yes | Only fixed `pause(n)` — no `pause(min, max)` variance. Identical pauses produce unrealistically synchronised load. |
| GAT013 | MissingHTTP2 | info | yes | HTTPS base URL but HTTP/2 not enabled. Opens a new connection per request instead of multiplexing. |

---

## Quality scoring

Every file receives a quality score from 0 to 100 and a letter grade.

**Formula:**
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

A clean file with no violations scores 100 (A). A file with 1 error and 3 warnings scores `100 − 15 − 15 = 70` (C).

The score appears in text output as a badge (`[D 55/100]`), in JSON output as `quality_score`/`quality_grade` fields on each file and an `overall_score`/`overall_grade` on the top-level result, and can be used as a CI gate.

---

## Auto-fix

25 rules have safe auto-fix implementations. When a violation is fixable, it is marked `[fixable]` in text output even when no fix flag is passed.

```bash
# Preview what would change (unified diff, no files written)
perf-lint check my-test.js --fix-dry-run

# Apply fixes in place, then report remaining violations
perf-lint check my-test.js --fix
```

**`--fix-dry-run`** is safe to run in CI to audit what `--fix` would do. It cannot be combined with `--fix`.

All fixes are insertion-only or simple substitution — no logic is changed. If a fix cannot be applied safely (e.g. the element already exists), it is skipped silently and the violation remains in the report.

**Fixable by framework:**

- **JMeter (18 rules):** JMX001–002, JMX005–006, JMX009–012, JMX014–015, JMX017–023, JMX025 — insert missing managers, add assertions, replace BeanShell with JSR223, add timeouts, fix greedy regex patterns.
- **k6 (7 rules):** K6001, K6003–004, K6006–007, K6010, K6012 — add `sleep()`, add `check()`, add thresholds, add `teardown()`, add tags, add `gracefulStop`.
- **Gatling (7 rules):** GAT003–004, GAT006, GAT008–009, GAT012–013 — add assertions, adjust ramp-up, add `maxDuration()`, add timeouts, add HTTP/2.

---

## CLI reference

```
perf-lint check <PATH...> [OPTIONS]

Arguments:
  PATH  One or more files or directories to analyse. Directories are
        searched recursively for .jmx, .js, .ts, .scala, and .kt files.

Options:
  --format [text|json|sarif]   Output format (default: text)
  --config FILE                Path to .perf-lint.yml (auto-detected if absent)
  --severity [error|warning|info]
                               Override severity threshold for exit code 1
  --no-color                   Disable colour output
  --output FILE                Write output to FILE instead of stdout
  --ignore-rule RULE_ID        Ignore a rule (repeatable: --ignore-rule K6001 --ignore-rule K6004)
  --fix                        Apply safe fixes to the file system, then re-lint
  --fix-dry-run                Show what --fix would change without writing files
  --version                    Show version and exit

perf-lint rules [--framework jmeter|k6|gatling] [--json]
  List all available rules.

perf-lint init [--output FILE]
  Generate a starter .perf-lint.yml in the current directory.
```

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | No violations at/above the severity threshold |
| 1 | One or more violations at/above the threshold |
| 2 | Tool error (bad config, parse failure, invalid flag combination) |

---

## Configuration

Run `perf-lint init` to generate a starter `.perf-lint.yml`. perf-lint searches for the config file by walking up from the current directory, so you can place it at the repository root and it will apply to all subdirectories.

```yaml
# .perf-lint.yml
version: 1

# Violations at or above this severity cause exit code 1
# Options: error | warning | info (default: warning)
severity_threshold: warning

rules:
  # Disable a rule entirely
  JMX003:
    enabled: false

  # Escalate severity
  K6001:
    severity: error

  # Both at once
  GAT005:
    enabled: false

# Custom rule plugins (glob supported)
custom_rules:
  - path: ./lint_rules/*.py

# Paths to skip (glob, supports **)
ignore_paths:
  - "**/node_modules/**"
  - "**/vendor/**"
  - "**/generated/**"
```

Command-line flags always override config file settings. `--ignore-rule` adds to (not replaces) any rules disabled in the config.

---

## Output formats

### Text (default)

Human-readable, coloured output with per-file score badges and a summary table. Pass `--no-color` for CI environments that don't support ANSI codes.

### JSON

Structured output suitable for processing in CI pipelines, dashboards, or custom tooling.

```json
{
  "overall_score": 72,
  "overall_grade": "C",
  "summary": {
    "files_checked": 2,
    "total_violations": 5,
    "errors": 1,
    "warnings": 3,
    "infos": 1
  },
  "files": [
    {
      "path": "tests/k6/ecommerce.js",
      "framework": "k6",
      "quality_score": 55,
      "quality_grade": "D",
      "violations": [
        {
          "rule_id": "K6001",
          "severity": "warning",
          "message": "No sleep() calls found...",
          "location": { "line": 1, "column": null, "element_path": null },
          "suggestion": "Add sleep(1) between requests to simulate think time.",
          "fix_example": "sleep(1);"
        }
      ],
      "summary": { "errors": 0, "warnings": 2, "infos": 0, "total": 2 }
    }
  ]
}
```

### SARIF 2.1.0

[Static Analysis Results Interchange Format](https://sarifweb.azurewebsites.net/) for native integration with GitHub Advanced Security, VS Code, and other SARIF-aware tools.

```bash
perf-lint check ./tests/ --format sarif --output results.sarif
```

---

## CI/CD integration

### GitHub Actions

```yaml
- name: Run perf-lint
  run: |
    pip install perf-lint
    perf-lint check ./performance-tests/ \
      --format sarif \
      --output perf-lint.sarif

- name: Upload SARIF to Code Scanning
  uses: github/codeql-action/upload-sarif@v3
  if: always()
  with:
    sarif_file: perf-lint.sarif
    category: perf-lint
```

To gate the build on quality score, combine with `jq`:

```yaml
- name: Quality gate — score must be B or above
  run: |
    score=$(perf-lint check ./performance-tests/ --format json \
      | jq '.overall_score')
    echo "Quality score: $score"
    [ "$score" -ge 75 ] || (echo "Score below B threshold" && exit 1)
```

### GitLab CI

```yaml
perf-lint:
  stage: test
  script:
    - pip install perf-lint
    - perf-lint check ./performance-tests/ --format json --output perf-lint.json
  artifacts:
    paths:
      - perf-lint.json
    when: always
  allow_failure: false
```

### Azure Pipelines

```yaml
- script: |
    pip install perf-lint
    perf-lint check ./performance-tests/ --format sarif --output $(Build.ArtifactStagingDirectory)/perf-lint.sarif
  displayName: 'Run perf-lint'

- task: PublishBuildArtifacts@1
  inputs:
    pathToPublish: '$(Build.ArtifactStagingDirectory)'
    artifactName: 'perf-lint-results'
```

---

## Custom rules

Create a Python file with a class decorated with `@RuleRegistry.register`. The class must:

- Set `rule_id`, `name`, `description`, `severity`, `frameworks`, and (optionally) `tags` as class attributes.
- Implement `check(self, ir: ScriptIR) -> list[Violation]`.
- Optionally implement `apply_fix(self, ir: ScriptIR) -> str | None` and set `fixable = True` to enable auto-fix.

```python
# lint_rules/custom_rule.py
from perf_lint.ir.models import Framework, Location, Severity, Violation
from perf_lint.rules.base import BaseRule, RuleRegistry


@RuleRegistry.register
class CUSTOM001NoComments(BaseRule):
    rule_id = "CUSTOM001"
    name = "NoComments"
    description = "Script has no inline comments — hard to maintain."
    severity = Severity.INFO
    frameworks = [Framework.K6]
    tags = ("maintainability",)

    def check(self, ir):
        if "//" not in ir.raw_content and "/*" not in ir.raw_content:
            return [
                Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message=self.description,
                    location=Location(line=1),
                    suggestion="Add comments explaining the test scenario and data requirements.",
                )
            ]
        return []
```

Reference it in `.perf-lint.yml`:

```yaml
custom_rules:
  - path: ./lint_rules/custom_rule.py   # single file
  - path: ./lint_rules/*.py             # glob
```

`ir.parsed_data` contains all pre-extracted data for the framework. The available keys are documented in the `JMeterParsedData`, `K6ParsedData`, and `GatlingParsedData` TypedDicts in `src/perf_lint/ir/models.py`. Rules should prefer `parsed_data` over re-scanning `ir.raw_content`.

---

## Development

```bash
# Clone
git clone https://github.com/markslilley/perf-lint.git
cd perf-lint

# Install in dev mode with all dev dependencies
pip install -e ".[dev]"

# Run the full test suite
pytest

# Run with coverage
pytest --cov=perf_lint --cov-report=term-missing

# Lint + type-check
ruff check src/ tests/
mypy src/

# Test the tool against its own sample scripts
perf-lint check samples/
perf-lint check samples/ --format json | python3 -m json.tool
```

See [CLAUDE.md](CLAUDE.md) for architecture documentation, conventions, and guidance on adding new rules.

---

## License

MIT — see [LICENSE](LICENSE).
