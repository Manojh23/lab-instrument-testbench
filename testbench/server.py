"""Local-only newline-delimited JSON device protocol, not a real vendor protocol."""
import argparse
import json
import socketserver
import threading
import time

from .controller import Controller, Rejected


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(2)
        try:
            raw = self.rfile.readline(8193)
            if len(raw) > 8192 or not raw.endswith(b'\n'):
                self.wfile.write(b'{"ok":false,"error":"invalid frame"}\n')
                return
            try:
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    raise Rejected('object required')
                op = msg.get('op')
                controller = self.server.controller
                if op == 'status' and set(msg) == {'op'}:
                    result = controller.status()
                elif op == 'audit' and set(msg) == {'op'}:
                    result = controller.audit()
                elif op == 'telemetry' and set(msg) == {'op', 'sample'}:
                    result = controller.telemetry(msg['sample'])
                elif op == 'command' and set(msg) == {'op','id','operation','args'}:
                    result = controller.command(msg['id'], msg['operation'], msg['args'])
                else:
                    raise Rejected('invalid request schema')
                response = {'ok': True, 'result': result}
            except (ValueError, TypeError, KeyError) as error:
                response = {'ok': False, 'error': str(error)}
            self.wfile.write(json.dumps(response, allow_nan=False).encode()+b'\n')
        except (TimeoutError, ConnectionError):
            return


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = False
    block_on_close = True

    def __init__(self, address, controller):
        self.controller = controller
        self.stop_monitor = threading.Event()
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def monitor(self):
        while not self.stop_monitor.wait(.1):
            self.controller.status()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--database', default='instrument.sqlite')
    args = parser.parse_args()
    controller = Controller(args.database)
    with Server(('127.0.0.1', args.port), controller) as server:
        monitor = threading.Thread(target=server.monitor, daemon=True)
        monitor.start()
        print(json.dumps({'listening': server.server_address[1]}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.stop_monitor.set()
            monitor.join(timeout=1)
    controller.close()


if __name__ == '__main__':
    main()
