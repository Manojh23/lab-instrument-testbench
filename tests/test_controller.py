from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from testbench.controller import Controller, Rejected


@pytest.mark.requirement('REQ-01')
@pytest.mark.parametrize('field,bad', [(k,v) for k,upper in [('top_flow',1000),('bottom_flow',1000),('stretch',20),('frequency',2)]
                         for v in [-.01, upper+.01, float('nan'), float('inf'), True, '1', None]])
def test_invalid_setpoints_leave_state_unchanged(controller, config, field, bad):
    config[field] = bad
    with pytest.raises(Rejected):
        controller.command('invalid', 'configure', config)
    assert controller.status()['config'] is None
    assert controller.audit() == []


@pytest.mark.requirement('REQ-01')
@pytest.mark.parametrize('edge', [0, 1])
def test_setpoint_boundaries(controller, edge):
    cfg = {k:edge*upper for k,upper in [('top_flow',1000),('bottom_flow',1000),('stretch',20),('frequency',2)]}
    assert controller.command('config', 'configure', cfg)['config'] == cfg


@pytest.mark.requirement('REQ-02')
def test_start_requires_configuration_and_sensor(controller, config, sensor):
    with pytest.raises(Rejected):
        controller.command('no-config', 'start')
    controller.command('configure','configure',config)
    with pytest.raises(Rejected):
        controller.command('no-sensor', 'start')
    controller.telemetry(sensor())
    assert controller.command('start', 'start')['outputs_enabled']
    assert not controller.command('stop', 'stop')['outputs_enabled']


@pytest.mark.requirement('REQ-01')
def test_configuration_cannot_change_while_running(controller, config, sensor):
    controller.command('c','configure',config)
    controller.telemetry(sensor())
    controller.command('s','start')
    with pytest.raises(Rejected):
        controller.command('edit','configure',dict(config, top_flow=110))
    returned = controller.status()
    returned['config']['top_flow'] = 999
    assert controller.status()['config']['top_flow'] == 100


@pytest.mark.requirement('REQ-03')
@pytest.mark.parametrize('changes', [{'seq':1},{'seq':0},{'seq':True},{'seq':2,'sampled_at':97.9},
                                     {'seq':2,'sampled_at':100.1},{'seq':2,'pressure':float('nan')}])
def test_bad_sensor_packet_does_not_replace_latest(controller, sensor, changes):
    controller.telemetry(sensor())
    sample = sensor(seq=2)
    sample.update(changes)
    with pytest.raises(Rejected):
        controller.telemetry(sample)
    assert controller.status()['last_seq'] == 1


@pytest.mark.requirement('REQ-03')
def test_out_of_order_sample_time(controller, sensor, clock):
    controller.telemetry(sensor())
    clock.value += 1
    with pytest.raises(Rejected):
        controller.telemetry(sensor(seq=2, sampled_at=99.9))


@pytest.mark.requirement('REQ-04')
@pytest.mark.parametrize('age,fault', [(2,False),(2.001,True)])
def test_watchdog_boundary(controller, config, sensor, clock, age, fault):
    controller.command('c','configure',config)
    controller.telemetry(sensor())
    controller.command('s','start')
    clock.value += age
    state = controller.status()
    assert (state['state']=='FAULT') == fault
    assert state['outputs_enabled'] != fault


@pytest.mark.requirement('REQ-04')
def test_stale_sensor_cannot_start(controller, config, sensor, clock):
    controller.command('c','configure',config)
    controller.telemetry(sensor())
    clock.value += 2.01
    with pytest.raises(Rejected, match='fresh telemetry'):
        controller.command('start','start')
    assert not controller.status()['outputs_enabled']


@pytest.mark.requirement('REQ-05')
@pytest.mark.parametrize('pressure,expected', [(120,'RUNNING'),(120.01,'FAULT')])
def test_pressure_trip_boundary(controller, config, sensor, pressure, expected):
    controller.command('c','configure',config)
    controller.telemetry(sensor())
    controller.command('s','start')
    assert controller.telemetry(sensor(seq=2, pressure=pressure))['state']==expected


@pytest.mark.requirement('REQ-05')
def test_pressure_interlock_blocks_start(controller, config, sensor):
    controller.command('c','configure',config)
    controller.telemetry(sensor(pressure=121))
    with pytest.raises(Rejected, match='pressure interlock'):
        controller.command('s','start')


@pytest.mark.requirement('REQ-06')
def test_three_consecutive_flow_faults_and_recovery(controller, config, sensor):
    controller.command('c','configure',config)
    controller.telemetry(sensor())
    controller.command('s','start')
    for seq in [2,3]:
        assert controller.telemetry(sensor(seq=seq,top_flow=120))['state']=='RUNNING'
    controller.telemetry(sensor(seq=4))
    for seq in [5,6]:
        assert controller.telemetry(sensor(seq=seq,top_flow=120))['state']=='RUNNING'
    state = controller.telemetry(sensor(seq=7,top_flow=120))
    assert state['fault']=='flow_deviation' and not state['outputs_enabled']


@pytest.mark.requirement('REQ-07')
def test_fault_latches_and_explicit_reset_requires_fresh_safe_reading(controller, config, sensor, clock):
    controller.command('c','configure',config)
    controller.telemetry(sensor())
    controller.command('s','start')
    controller.telemetry(sensor(seq=2,pressure=150))
    assert controller.command('stop','stop')['state']=='FAULT'
    with pytest.raises(Rejected):
        controller.command('unsafe-reset','reset')
    controller.telemetry(sensor(seq=3))
    assert controller.status()['state']=='FAULT'
    clock.value += 3
    with pytest.raises(Rejected):
        controller.command('stale-reset','reset')
    controller.telemetry(sensor(seq=4))
    state = controller.command('reset','reset')
    assert state['state']=='IDLE' and state['config'] is None and not state['outputs_enabled']


@pytest.mark.requirement('REQ-08')
def test_retries_conflicts_and_audit(controller, config):
    first = controller.command('same','configure',config)
    assert not first['replayed']
    assert controller.command('same','configure',config)['replayed']
    with pytest.raises(Rejected, match='reused'):
        controller.command('same','configure',dict(config,stretch=11))
    assert len(controller.audit()) == 1


@pytest.mark.requirement('REQ-08')
def test_database_failure_rolls_back_memory_and_command(controller, config):
    controller.db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(FAIL,'injected disk failure'); END")
    with pytest.raises(sqlite3.Error):
        controller.command('c','configure',config)
    assert controller.status()['config'] is None and controller.audit()==[]
    controller.db.execute('DROP TRIGGER fail_audit')
    assert not controller.command('c','configure',config)['replayed']


@pytest.mark.requirement('REQ-09')
def test_restart_requires_review(tmp_path, clock, config, sensor):
    path = str(tmp_path/'restart.sqlite')
    c = Controller(path, clock)
    c.command('c','configure',config)
    c.telemetry(sensor())
    c.command('s','start')
    c.close()
    c = Controller(path, clock)
    try:
        state = c.status()
        assert state['state']=='FAULT' and state['fault']=='restart_requires_review'
        assert not state['outputs_enabled'] and len(c.audit())==3
        assert c.command('s','start')['replayed']
        assert not c.status()['outputs_enabled']
    finally:
        c.close()


@pytest.mark.requirement('REQ-11')
def test_concurrent_retries_apply_once(controller, config):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _:controller.command('one','configure',config),range(20)))
    assert sum(not r['replayed'] for r in results)==1
    assert len(controller.audit())==1
