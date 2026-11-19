# Verification plan

**Scope:** Software-only flow/stretch instrument simulator and local transport, version 0.1. All thresholds are fictional engineering requirements. No physical Emulate instrument, cells, samples, or vendor firmware are involved.

## Approach

1. Maintain acceptance criteria in `requirements.json`. Each pytest case must reference a known requirement ID. Collection fails for an unmapped case.
2. Exercise parameter equivalence classes and exact boundaries, state transitions, invalid inputs, fault latching, transactional failures, repeated commands and concurrency.
3. Use a virtual monotonic clock for deterministic timing boundaries; avoid real sleeps in controller tests.
4. Start the simulator in separate processes for transport tests. Send fragmented/invalid frames, retry commands, let a partial frame time out, reconnect, and stop telemetry while the independent watchdog runs.
5. Deliberately bypass freshness in a test-only subclass. Require the existing stale-start test to fail with an assertion. A crash, setup error or missing report does not count as detection.
6. Produce JUnit XML, coverage XML, JSON requirement traceability, and an HTML verification summary. Retain the deliberate-failure console and JUnit evidence separately from the passing verification suite.

## Entry criteria

- Linux or a compatible Unix development host with Python 3.11+ and the declared test dependencies.
- No hardware connected; TCP listener restricted to loopback.
- Requirements and tests reviewed together whenever the protocol or controller changes.

## Exit criteria

- All normal test cases pass with no missing requirement identifiers.
- All twelve requirements have passing mapped cases.
- The intentionally defective freshness check is detected by the original stale-start case.
- No unexplained failures or skipped verification cases.
- Physical hardware behavior, calibration, actuator response, electrical faults, regulatory compliance and biological performance remain outside the evidence.

## Change workflow

Document the user-visible expectation, update the requirement and test case, reproduce the defect before changing controller logic, make a focused fix, run the full verification script, then review reports and the affected acceptance criterion. Record a defect with steps, expected/actual behavior, environment, logs, suspected root cause, and retest evidence. `defect-001.md` provides an executed example. These Markdown records are local test-management artifacts; no Jira or Xray integration is claimed.

## Manual demonstration

Run `bash scripts/check.sh`, open `reports/verification.html`, inspect REQ-04 and REQ-12, then open `reports/regression/console.txt`. The normal case rejects a stale start; the intentionally defective test double allows it and the same case fails. Explain why a passing test run alone would not establish that the test catches the failure it was written to detect.

## Known limitations

- The TCP protocol is invented. It is not Emulate's device API.
- Timing tests establish logical boundaries and a loopback watchdog, not real-time guarantees.
- One controller process owns each SQLite database; multiple independent writers are unsupported.
- TCP has no authentication or encryption and binds only to localhost. Never expose this simulator publicly.
- A command retry returns current status plus the original state and a replay flag; it never resumes an old run.
- The Dockerfile and Jenkinsfile are supplied for CI use; local verification runs directly on Linux, not on a Jenkins server or physical device.
