# Coverage Lab sample

A deliberately under-tested application in **Python and JavaScript** for testing
[Coverage Lab](../ai-coverage-lab/) end-to-end.
All existing tests pass. Missing coverage is intentional, not a CI failure.

## Python

`invoice.py` calculates customer discounts, shipping and refunds with `Decimal`.
The tests cover standard orders, small-order shipping and a VIP express order.
Student pricing, invalid inputs and the refund schedule are deliberately incomplete.

```powershell
python -m unittest discover -s tests -v
```

## JavaScript

`javascript/pricing.js` calculates domestic/international shipping and loyalty
discounts. The tests cover only domestic shipping. Node.js **22+** is required;
there are no npm dependencies.

```powershell
npm test
npm run coverage
```

The coverage script uses Node's built-in instrumentation and writes
`coverage/lcov.info`. This file is generated and ignored by Git.

## Measure both with Coverage Lab

After installing Coverage Lab:

```powershell
coverage-lab run . --runner python --output python-report.json
coverage-lab run . --runner npm --output js-report.json
coverage-lab serve
```

Upload a generated JSON file at http://127.0.0.1:8765. Because this repository
contains both toolchains, choose `--runner` explicitly. To repeat npm measurement,
move/remove the exact `coverage/lcov.info` file first, or import it directly.

From the sibling Coverage Lab directory:

```powershell
python scripts\e2e.py ..\ai-coverage-sample --browser
```

An optional `--ai` request uses your configured OpenAI-compatible provider to
suggest scenarios for the measured gaps. Generated suggestions are unverified;
add tests and rerun to prove an improvement. No AI credentials are required to run
either sample's tests or measure their coverage.

The main project's [`scripts/e2e.py`](../ai-coverage-lab/scripts/e2e.py)
copies this repo into a temporary directory, executes both suites and validates
the analyzer and browser dashboard against their real results.

MIT licensed.
