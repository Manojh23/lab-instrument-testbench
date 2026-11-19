from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import time

import pytest

from testbench.client import exchange

pytestmark = [pytest.mark.integration, pytest.mark.requirement('REQ-10')]


@pytest.fixture
def device(tmp_path):
    process = subprocess.Popen([sys.executable,'-m','testbench.server','--port','0',
                                '--database',str(tmp_path/'device.sqlite')],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        ready, _, _ = select.select([process.stdout],[],[],5)
        if not ready:
            raise RuntimeError('simulator did not announce its port')
        line = process.stdout.readline()
        if not line:
            raise RuntimeError(process.stderr.read())
        port = json.loads(line)['listening']
        yield port
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdout.close()
        process.stderr.close()


def raw(port, data):
    with socket.create_connection(('127.0.0.1',port),timeout=3) as sock:
        sock.sendall(data)
        return json.loads(sock.makefile('rb').readline())


def test_fragmented_frame_and_reconnection(device):
    with socket.create_connection(('127.0.0.1',device),timeout=3) as sock:
        sock.sendall(b'{"op":')
        sock.sendall(b'"status"}\n')
        response = json.loads(sock.makefile('rb').readline())
        assert response['ok'] and response['result']['state']=='IDLE'
    assert exchange(device,{'op':'status'})['ok']


@pytest.mark.parametrize('payload', [b'{broken\n', b'[]\n', b'{"op":"start"}\n',
                                      b'{"op":"status","extra":1}\n', b'x'*8193+b'\n'])
def test_invalid_frame_rejected_without_state_change(device,payload):
    assert not raw(device,payload)['ok']
    assert exchange(device,{'op':'status'})['result']['state']=='IDLE'
    assert exchange(device,{'op':'audit'})['result']==[]


def test_partial_frame_times_out_then_reconnects(device):
    with socket.create_connection(('127.0.0.1',device),timeout=3) as sock:
        sock.sendall(b'{"op":')
        assert sock.recv(1)==b''
    assert exchange(device,{'op':'status'})['ok']


@pytest.mark.requirement('REQ-04')
def test_watchdog_runs_without_status_polling(device,config):
    assert exchange(device,{'op':'command','id':'cfg','operation':'configure','args':config})['ok']
    sample = {'seq':1,'sampled_at':time.monotonic(),'top_flow':100,'bottom_flow':80,'pressure':40}
    assert exchange(device,{'op':'telemetry','sample':sample})['ok']
    assert exchange(device,{'op':'command','id':'start','operation':'start','args':{}})['result']['outputs_enabled']
    # No status read triggers the watchdog; the server's independent monitor must do it.
    time.sleep(2.25)
    events = exchange(device,{'op':'audit'})['result']
    assert any(e['detail'].get('reason')=='sensor_timeout' for e in events)
    assert not exchange(device,{'op':'status'})['result']['outputs_enabled']


@pytest.mark.requirement('REQ-11')
def test_concurrent_wire_command_retries(device,config):
    msg = {'op':'command','id':'same','operation':'configure','args':config}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _:exchange(device,msg),range(12)))
    assert all(r['ok'] for r in results)
    assert sum(not r['result']['replayed'] for r in results)==1
    assert len(exchange(device,{'op':'audit'})['result'])==1
