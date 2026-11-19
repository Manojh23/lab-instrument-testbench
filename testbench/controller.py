"""Illustrative flow/stretch controller with latched faults and a durable audit trail.

All numeric operating limits are invented test specifications, not Emulate settings.
"""
import hashlib
import json
import math
import sqlite3
import threading
import time


class Rejected(ValueError):
    """A command violates the documented controller contract."""


def number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise Rejected('finite number required')
    if not low <= value <= high:
        raise Rejected('value outside illustrative limits')
    return float(value)


class Controller:
    def __init__(self, database, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.RLock()
        self.db = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS commands (id TEXT PRIMARY KEY, digest TEXT NOT NULL, response TEXT NOT NULL);
        ''')
        self.state = 'IDLE'
        self.config = None
        self.fault = None
        self.latest = None
        self.flow_violations = 0
        self.last_seq = -1
        row = self.db.execute('SELECT value FROM state WHERE id=1').fetchone()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if row and row[0] in ('RUNNING', 'FAULT'):
                self.state, self.fault = 'FAULT', 'restart_requires_review'
                self._event('fault', {'reason': self.fault})
            self._persist()
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def close(self):
        self.db.close()

    def _event(self, kind, detail):
        self.db.execute('INSERT INTO audit(at,kind,detail) VALUES(?,?,?)',
                        (self.clock(), kind, json.dumps(detail, allow_nan=False)))

    def _persist(self):
        self.db.execute('INSERT INTO state(id,value) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value', (self.state,))

    def _fresh(self):
        return self.latest is not None and 0 <= self.clock()-self.latest['sampled_at'] <= 2.0

    def _latch(self, reason):
        if self.state != 'FAULT':
            self.state, self.fault = 'FAULT', reason
            self._event('fault', {'reason': reason})
            self._persist()

    def _tick(self):
        if self.state == 'RUNNING' and not self._fresh():
            self._latch('sensor_timeout')

    def status(self):
        with self.lock:
            self._tick()
            return {'state': self.state, 'fault': self.fault, 'config': dict(self.config) if self.config else None,
                    'outputs_enabled': self.state == 'RUNNING', 'last_seq': self.last_seq}

    def audit(self):
        with self.lock:
            return [{'seq': seq, 'at': at, 'kind': kind, 'detail': json.loads(detail)}
                    for seq, at, kind, detail in self.db.execute('SELECT seq,at,kind,detail FROM audit ORDER BY seq')]

    def telemetry(self, sample):
        with self.lock:
            required = {'seq', 'sampled_at', 'top_flow', 'bottom_flow', 'pressure'}
            if not isinstance(sample, dict) or set(sample) != required:
                raise Rejected('invalid telemetry schema')
            seq = sample['seq']
            if isinstance(seq, bool) or not isinstance(seq, int) or seq <= self.last_seq:
                raise Rejected('sequence must increase')
            stamp = number(sample['sampled_at'], 0, 1e15)
            if not 0 <= self.clock()-stamp <= 2.0:
                raise Rejected('stale or future telemetry')
            if self.latest and stamp < self.latest['sampled_at']:
                raise Rejected('sample time moved backwards')
            clean = {'seq': seq, 'sampled_at': stamp,
                     'top_flow': number(sample['top_flow'], 0, 2000),
                     'bottom_flow': number(sample['bottom_flow'], 0, 2000),
                     'pressure': number(sample['pressure'], 0, 200)}
            self.latest, self.last_seq = clean, seq
            if self.state == 'RUNNING':
                if clean['pressure'] > 120:
                    self._latch('overpressure')
                else:
                    off_target = any(abs(clean[k]-self.config[k]) > max(1, .1*self.config[k])
                                     for k in ('top_flow', 'bottom_flow'))
                    self.flow_violations = self.flow_violations+1 if off_target else 0
                    if self.flow_violations >= 3:
                        self._latch('flow_deviation')
            return self.status()

    def command(self, command_id, operation, args=None):
        args = {} if args is None else args
        if not isinstance(command_id, str) or not 1 <= len(command_id) <= 100 or not isinstance(args, dict):
            raise Rejected('invalid command ID or arguments')
        try:
            payload = json.dumps([operation, args], sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise Rejected('invalid JSON values') from error
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self.lock:
            self._tick()
            old = self.db.execute('SELECT digest,response FROM commands WHERE id=?', (command_id,)).fetchone()
            if old:
                if old[0] != digest:
                    raise Rejected('command ID reused with different content')
                return dict(self.status(), replayed=True, original_state=json.loads(old[1])['state'])
            before = (self.state, self.config, self.fault, self.flow_violations)
            self.db.execute('BEGIN IMMEDIATE')
            try:
                if operation == 'configure':
                    if self.state != 'IDLE' or set(args) != {'top_flow','bottom_flow','stretch','frequency'}:
                        raise Rejected('configure requires IDLE and all setpoints')
                    self.config = {k: number(args[k], 0, high) for k, high in
                                   [('top_flow',1000),('bottom_flow',1000),('stretch',20),('frequency',2)]}
                elif operation == 'start':
                    if args or self.state != 'IDLE' or self.config is None or not self._fresh():
                        raise Rejected('start requires configuration and fresh telemetry in IDLE')
                    if self.latest['pressure'] > 120:
                        raise Rejected('pressure interlock')
                    self.state, self.flow_violations = 'RUNNING', 0
                elif operation == 'stop':
                    if args:
                        raise Rejected('stop takes no arguments')
                    if self.state != 'FAULT':
                        self.state = 'IDLE'
                elif operation == 'reset':
                    if args or self.state != 'FAULT' or not self._fresh() or self.latest['pressure'] > 120:
                        raise Rejected('reset requires a fault and fresh safe telemetry')
                    self.state, self.fault, self.config, self.flow_violations = 'IDLE', None, None, 0
                else:
                    raise Rejected('unknown command')
                self._event('command', {'id': command_id, 'operation': operation, 'state': self.state})
                self._persist()
                response = dict(self.status(), replayed=False)
                self.db.execute('INSERT INTO commands VALUES(?,?,?)', (command_id, digest, json.dumps(response)))
                self.db.execute('COMMIT')
                return response
            except Exception:
                self.db.execute('ROLLBACK')
                self.state, self.config, self.fault, self.flow_violations = before
                raise
