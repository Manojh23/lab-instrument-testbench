"""Short, deterministic walkthrough with no real hardware or waiting."""
from pathlib import Path
import tempfile

from testbench.controller import Controller


class Clock:
    value = 100.0
    def __call__(self):
        return self.value


with tempfile.TemporaryDirectory() as root:
    clock = Clock()
    controller = Controller(str(Path(root)/'demo.sqlite'), clock)
    try:
        def show(label):
            status = controller.status()
            print(f"{label}: state={status['state']}, outputs={status['outputs_enabled']}, fault={status['fault']}")
            return status
        def reading(seq, flow=100):
            return {'seq':seq,'sampled_at':clock(),'top_flow':flow,'bottom_flow':80,'pressure':40}
        controller.command('configuration','configure',{'top_flow':100,'bottom_flow':80,'stretch':10,'frequency':1})
        controller.telemetry(reading(1))
        controller.command('begin','start')
        assert show('1. Configured and started')['outputs_enabled']
        for seq in [2,3,4]:
            controller.telemetry(reading(seq,flow=120))
        assert show('2. Three out-of-tolerance readings')['fault']=='flow_deviation'
        controller.telemetry(reading(5))
        assert show('3. Sensor recovers; fault stays latched')['state']=='FAULT'
        controller.command('reviewed-reset','reset')
        assert show('4. Explicit reset; configuration cleared')['config'] is None
        print('Audit records:',len(controller.audit()))
        print('Next: bash scripts/check.sh; open reports/verification.html')
    finally:
        controller.close()
