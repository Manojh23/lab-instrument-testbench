import json
import socket


def exchange(port, message, timeout=2):
    with socket.create_connection(('127.0.0.1', port), timeout=timeout) as connection:
        connection.sendall(json.dumps(message, allow_nan=False).encode()+b'\n')
        with connection.makefile('rb') as stream:
            raw = stream.readline(1_048_577)
            if len(raw) > 1_048_576 or not raw.endswith(b'\n'):
                raise ValueError('incomplete or oversized response')
            return json.loads(raw)
