import html
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

import pytest

from testbench.controller import Controller

ROOT = Path(__file__).resolve().parents[1]
requirements = json.loads((ROOT/'docs/requirements.json').read_text())
cases = {}


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def controller(tmp_path, clock):
    cls = Controller
    # Deliberate regression stays in test code, never in the shipped simulator.
    if os.getenv('INJECT_STALE_REGRESSION') == '1':
        class DefectiveController(Controller):
            def _fresh(self):
                return self.latest is not None
        cls = DefectiveController
    c = cls(str(tmp_path/'state.sqlite'), clock)
    yield c
    c.close()


@pytest.fixture
def config():
    return {'top_flow': 100, 'bottom_flow': 80, 'stretch': 10, 'frequency': 1}


@pytest.fixture
def sensor(clock):
    def sample(seq=1, **changes):
        return dict({'seq': seq, 'sampled_at': clock(), 'top_flow': 100,
                     'bottom_flow': 80, 'pressure': 40}, **changes)
    return sample


def pytest_collection_modifyitems(items):
    cases.clear()
    for item in items:
        ids = [m.args[0] for m in item.iter_markers('requirement')]
        if not ids or any(i not in requirements for i in ids):
            raise pytest.UsageError(f'{item.nodeid}: missing or unknown requirement ID')
        cases[item.nodeid] = {'requirements': ids, 'outcome': 'not_run', 'seconds': 0}


def pytest_runtest_logreport(report):
    case = cases[report.nodeid]
    case['seconds'] += report.duration
    if report.failed:
        case['outcome'] = 'failed'
        case['failure'] = str(report.longrepr)
    elif report.skipped and case['outcome'] != 'failed':
        case['outcome'] = 'skipped'
    elif report.when == 'call' and case['outcome'] != 'failed':
        case['outcome'] = report.outcome


def pytest_sessionfinish(session, exitstatus):
    out = Path(os.getenv('REPORT_DIR', 'reports'))
    out.mkdir(parents=True, exist_ok=True)
    sha = os.getenv('SOURCE_COMMIT', '')
    if not sha and shutil.which('git'):
        sha = subprocess.run(['git','rev-parse','HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    sha = sha or 'uncommitted-or-not-available'
    rows = []
    for req, description in requirements.items():
        matched = [{'test': name, **case} for name, case in cases.items() if req in case['requirements']]
        status = 'not_run' if not matched else ('failed' if any(c['outcome']=='failed' for c in matched)
                 else 'passed' if all(c['outcome']=='passed' for c in matched) else 'incomplete')
        rows.append({'id': req, 'description': description, 'status': status, 'cases': matched})
    payload = {'scope': 'Software-only prototype, no physical hardware or regulatory validation',
               'python': platform.python_version(), 'platform': platform.platform(), 'git_commit': sha,
               'pytest_exit': int(exitstatus), 'requirements': rows}
    (out/'traceability.json').write_text(json.dumps(payload, indent=2))
    table = ''.join('<tr><td>'+html.escape(r['id'])+'</td><td>'+html.escape(r['description'])+
                    '</td><td>'+r['status']+'</td><td>'+str(len(r['cases']))+'</td></tr>' for r in rows)
    failures = ''.join('<h3>'+html.escape(name)+'</h3><pre>'+html.escape(case.get('failure',''))+'</pre>'
                       for name, case in cases.items() if case['outcome']=='failed')
    (out/'verification.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8">
      <title>Instrument Verification Report</title><style>
      body{font:16px/1.5 system-ui;max-width:1100px;margin:40px auto;padding:0 20px;color:#17212b}
      table{border-collapse:collapse;width:100%}td,th{border:1px solid #cbd5df;padding:12px;text-align:left}
      pre{white-space:pre-wrap;background:#f3f5f7;padding:16px}h1{margin-bottom:0}
      </style><h1>Instrument Verification Report</h1><p>Software simulation only. No physical-device validation.</p>
      <p>Commit: '''+html.escape(sha)+''' | Python '''+platform.python_version()+'''</p>
      <table><tr><th>Requirement</th><th>Acceptance criterion</th><th>Result</th><th>Cases</th></tr>'''+table+'</table>'+failures+'</html>')
