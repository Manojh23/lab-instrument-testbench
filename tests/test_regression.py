import json
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.requirement('REQ-12')
def test_existing_contract_detects_deliberate_stale_regression():
    result = subprocess.run([sys.executable,'scripts/prove_regression.py'],
                            capture_output=True,text=True,timeout=20)
    assert result.returncode == 0, result.stdout+result.stderr
    proof = json.loads(Path('reports/regression/proof.json').read_text())
    assert proof['detected'] and proof['test'].endswith('test_stale_sensor_cannot_start')
