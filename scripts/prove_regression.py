"""Show that an intentionally defective freshness check is caught, not ignored."""
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

out = Path('reports/regression')
out.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, INJECT_STALE_REGRESSION='1', REPORT_DIR=str(out))
test = 'tests/test_controller.py::test_stale_sensor_cannot_start'
result = subprocess.run([sys.executable,'-m','pytest',test,'-q','--junitxml='+str(out/'junit.xml')],
                        env=env,capture_output=True,text=True)
(out/'console.txt').write_text(result.stdout+result.stderr)
if not (out/'junit.xml').exists():
    raise SystemExit('Regression experiment did not produce a test report')
tree = ET.parse(out/'junit.xml')
cases = tree.findall('.//testcase')
valid = (result.returncode==1 and len(cases)==1 and cases[0].get('name')=='test_stale_sensor_cannot_start'
         and len(cases[0].findall('failure'))==1 and not tree.findall('.//error'))
if not valid:
    print(result.stdout,result.stderr)
    raise SystemExit('Expected one stale-start assertion failure; experiment invalid')
(out/'proof.json').write_text(json.dumps({'detected':True,'test':test,'injection':'test-only freshness-check bypass'},indent=2))
print('PASS: stale-start regression detected by the existing contract test (one intentional failure recorded)')
