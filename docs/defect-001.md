# DEF-001: stale telemetry permits start

**Type:** Deliberately injected regression, detected by an executed test. Not a customer or vendor defect.

**Requirement:** REQ-04; detection capability REQ-12.

**Impact in this simulation:** Outputs can become enabled when the most recent sensor reading is older than the two-second freshness limit.

## Reproduce

1. Configure valid flow/stretch setpoints while IDLE.
2. Submit a normal reading at virtual time 100.00.
3. Advance time to 102.01 without another reading.
4. Issue start with a new command ID.

**Expected:** Reject start, remain IDLE, outputs disabled.

**Defective behavior:** The test-only subclass replaces the age check with `latest is not None`; start succeeds because a reading exists even though it is stale.

**Detection:** `python scripts/prove_regression.py` runs the existing stale-start case against that subclass. It requires exactly one named test assertion failure and rejects collection errors or crashes as invalid evidence. See `reports/regression/console.txt`, `junit.xml`, and `proof.json` after execution.

**Correct behavior:** The shipped controller requires `0 <= now - sampled_at <= 2.0`. Running `bash scripts/check.sh` checks that the correct implementation passes and the injected variant fails. The test double exists only in `tests/conftest.py` and cannot be enabled through the simulator CLI.
