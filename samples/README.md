# perf-lint sample scripts

Realistic performance test scripts to run perf-lint against. Each framework has a `*_good` and `*_bad` variant so you can compare what the linter catches.

## Quick start

```bash
# Scan everything at once
perf-lint check samples/

# Scan by framework
perf-lint check samples/k6/
perf-lint check samples/jmeter/
perf-lint check samples/gatling/

# See all violations with suggestions
perf-lint check samples/ --no-color

# Machine-readable output for CI
perf-lint check samples/ --format json
perf-lint check samples/ --format sarif --output results.sarif
```

## Sample files

### K6

| File | What it demonstrates |
|------|---------------------|
| `k6/ecommerce_good.js` | Full checkout flow — best practices: parameterised URL, thresholds, gradual stages, `check()`, `sleep()`, error handling |
| `k6/ecommerce_bad.js` | Same flow — **6 violations**: hardcoded IP, no sleep, no checks, no thresholds, aggressive stages, no error handling |
| `k6/api_spike_test.js` | REST API spike test — tests recovery after a traffic burst |

### JMeter

| File | What it demonstrates |
|------|---------------------|
| `jmeter/ecommerce_good.jmx` | Checkout flow with Cache Manager, Cookie Manager, CSV data sets, GaussianRandomTimer, variables, and response assertions |
| `jmeter/ecommerce_bad.jmx` | Same flow — **8 violations**: no cache/cookie managers, constant timer, ramp-up too short, no assertions, hardcoded IP, no CSV, no variables |

### Gatling

| File | What it demonstrates |
|------|---------------------|
| `gatling/EcommerceGoodSimulation.scala` | Checkout simulation — system-property base URL, CSV feeders, pause(), assertions, gradual ramp-up |
| `gatling/EcommerceBadSimulation.scala` | Same flow — **5 violations**: no pauses, hardcoded IP, no assertions, aggressive ramp-up, no feeder |

## Expected output

Running `perf-lint check samples/` should produce violations against all `*_bad` files and clean results for all `*_good` files:

```
samples/jmeter/ecommerce_bad.jmx  (jmeter)
  E [JMX004] Thread Group 1: ramp_time=10s for 500 threads (0.02s/thread)...
  E [JMX005] No assertions found. Tests that can't fail aren't tests...
  W [JMX001] No HTTP Cache Manager found...
  W [JMX002] No HTTP Cookie Manager found...
  W [JMX006] Sampler uses hardcoded IP '10.0.1.42'...
  W [JMX008] Found 4 samplers with no variable usage...
  I [JMX003] Only ConstantTimer found...
  I [JMX007] Found 4 samplers but no CSV Data Set...

samples/k6/ecommerce_bad.js  (k6)
  E [K6002] HTTP POST uses hardcoded IP URL: 'http://192.168.1.50/api/auth/login'...
  E [K6003] No check() calls found. Tests that can't detect failures aren't tests...
  W [K6001] No sleep() calls found...
  W [K6004] No thresholds defined...
  W [K6005] No error handling detected...
  W [K6006] First stage ramps to 500 users in 5s...

samples/gatling/EcommerceBadSimulation.scala  (gatling)
  E [GAT002] baseUrl uses hardcoded IP: 'http://10.0.1.42:8080'...
  E [GAT003] No assertions found...
  W [GAT001] Found 4 exec() calls but no pause() calls...
  W [GAT004] Ramp-up rate of 200.0 users/second...
  I [GAT005] Found 4 exec() calls but no feeder...
```
