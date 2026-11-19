# Lab Instrument Testbench

A software test-engineering project for an instrument with independent flow channels, stretch setpoints and sensor alarms. It combines a small Python controller with pytest verification, fault injection, real TCP process tests, a durable SQLite audit trail, requirement-to-test traceability, and CI configuration.

The use case was inspired by the flow, stretch and alert functions described on [Emulate's public culture-module page](https://emulatebio.com/zoe-cm2/). This is an independent **software-only simulation**, not Emulate software, a vendor protocol, a physical-device integration or a clinically validated product. All numeric limits are invented test specifications.

## Run the verification suite

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
bash scripts/check.sh
```

Open `reports/verification.html` to see the acceptance criteria and their results. `reports/traceability.json` lists the exact cases mapped to each requirement; `reports/junit.xml` and `coverage.xml` are machine-readable CI artifacts. Coverage includes the separate simulator subprocesses. The intentionally failing regression experiment is recorded under `reports/regression/`, separately from the normal passing suite.

For a short walkthrough, run `python scripts/demo.py`. It starts a configured run, injects three out-of-tolerance readings, shows the fault staying latched after a healthy reading, and performs an explicit reset. It uses virtual time and a temporary database.

Local verification on Linux/Python 3.12 completed with **61 passing cases**, all **12 requirements** mapped to passing cases, and **93% combined statement/branch coverage**. The deliberately defective freshness check was detected. These are software-test results, not hardware performance results.

## What is being tested

| Area | Verification behavior |
| --- | --- |
| Setpoint validation | Valid boundaries, values just outside the range, strings, booleans, missing values, NaN/Infinity, and attempted edits while running |
| State machine | IDLE/configure/start/stop, fresh-sensor prerequisites, pressure interlocks, latched FAULT, explicit reset and reconfiguration |
| Sensor faults | Stale/future/reordered readings, duplicate sequence numbers, overpressure, three consecutive flow deviations, recovery between deviations and missing heartbeat |
| Reliability | Retry-safe command IDs, conflicting reuse, concurrent retries, SQLite transaction rollback under an injected write failure, audit persistence and fail-stopped restart |
| Transport | Actual loopback TCP server processes, fragmented and malformed frames, message-size limits, incomplete-frame timeouts and reconnection |
| QA evidence | Twelve acceptance criteria, mandatory requirement markers, JUnit XML, HTML/JSON traceability, defect reproduction and regression-detection proof |
| DevOps | Bash verification entry point, Jenkins declarative pipeline, GitHub Actions Python matrix, Docker test packaging and archived reports |

## More than a passing test count

The suite includes a deliberate defect experiment. A **test-only** controller subclass incorrectly treats any previous reading as fresh. The original stale-start test must fail against it. The experiment verifies the exact failure, rejecting setup errors, crashes, and a missing report. That demonstrates that the regression case can detect its intended defect; it does not measure mutation coverage of the whole project.

Read the [test plan](docs/test-plan.md), [requirements](docs/requirements.json), and [executed defect example](docs/defect-001.md).

## Controller and protocol

```bash
python -m testbench.server --port 8765 --database instrument.sqlite
```

It binds **127.0.0.1 only** and accepts one newline-terminated JSON request per connection. `status`, `audit`, `telemetry`, and `command` operations are available through `testbench.client.exchange`. A sample status query:

```python
from testbench.client import exchange
print(exchange(8765, {"op": "status"}))
```

Configure uses `{"op":"command","id":"cfg-1","operation":"configure","args":{"top_flow":100,"bottom_flow":80,"stretch":10,"frequency":1}}`. Telemetry uses a strictly increasing integer sequence and the host's monotonic sample time, plus top/bottom flow and pressure. Start requires valid configuration and a reading no more than two seconds old. A monitor checks freshness every 100 ms while the process is running; tests do not claim a scheduling deadline on real hardware.

Successful commands and audit records commit in one SQLite transaction. Retry an identical ID/payload to obtain current status with `replayed: true`; changed content with the same ID is rejected. The `original_state` field identifies the state of the original acknowledgement. A restart never resumes RUNNING outputs, clears volatile telemetry/configuration, and requires review after an interrupted run.

## CI and Docker

The checked-in `Jenkinsfile` creates a venv, runs the same Bash verification entry point, publishes the normal JUnit report, and archives all evidence. It requires a Linux agent with Python and the Pipeline/JUnit plugins. It has not been executed on a Jenkins server.

GitHub Actions defines Python 3.11/3.12 verification jobs and a container test job. For local Docker use:

```bash
docker build -t instrument-tests .
docker run --rm instrument-tests
```

The image uses a non-root user. Local development verification was executed directly on Linux; Docker runtime execution is left to the configured CI/container environment. No cloud account, credentials, paid service, hardware driver, ROS2 installation or proprietary data is required.

## Scope

This project demonstrates software verification and QA processes around a simulated device boundary. It does not validate pumps, sensors, actual flow rates, biological samples, patient safety or regulatory compliance. It supports one process per database and is not designed as an internet-facing service.

### References

- [pytest parametrization](https://docs.pytest.org/en/stable/how-to/parametrize.html)
- [pytest output and JUnit](https://docs.pytest.org/en/stable/how-to/output.html)
- [Jenkinsfile documentation](https://www.jenkins.io/doc/book/pipeline/jenkinsfile/)
