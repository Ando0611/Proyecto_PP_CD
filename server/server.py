"""
Servidor - Calculadora Distribuida (Cómputo Distribuido, Proyecto Primer Parcial)

Responsabilidad única: lógica de negocio (resolver las operaciones
aritméticas) y persistencia de sus propios resultados. NO conoce a los
clientes directamente: toda la comunicación pasa por el middleware.

- Se conecta al middleware como socket cliente y se registra con rol "server".
- Recibe REQUEST (reenviados por el middleware desde cualquier cliente).
- Calcula el resultado (suma, resta, multiplicación, división).
- Persiste el resultado en una base SQLite propia (server_<id>.db).
- Envía el RESULT de vuelta al middleware, que lo distribuirá a todos los
  clientes conectados.

Uso:
    python server.py --id S1 --host 127.0.0.1 --port 5000
    python server.py --id S2 --host 127.0.0.1 --port 5000
"""

import argparse
import os
import socket
import sqlite3
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.protocol import MessageChannel, compute, make_register, make_result, now_iso  # noqa: E402

DB_DIR = os.path.join(os.path.dirname(__file__), "data")


class ResultStore:
    """Persistencia SQLite de los resultados procesados por este servidor."""

    def __init__(self, server_id: str):
        os.makedirs(DB_DIR, exist_ok=True)
        self.path = os.path.join(DB_DIR, f"server_{server_id}.db")
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                client_id TEXT NOT NULL,
                server_id TEXT NOT NULL,
                op TEXT NOT NULL,
                a REAL NOT NULL,
                b REAL NOT NULL,
                result REAL,
                status TEXT NOT NULL,
                error TEXT,
                timestamp TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def save(self, request_id, client_id, server_id, op, a, b, result, status, error, timestamp):
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO results
                    (request_id, client_id, server_id, op, a, b, result, status, error, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (request_id, client_id, server_id, op, a, b, result, status, error, timestamp),
            )
            self._conn.commit()


class CalcServer:
    def __init__(self, server_id: str, host: str, port: int):
        self.server_id = server_id
        self.host = host
        self.port = port
        self.store = ResultStore(server_id)
        self.channel: MessageChannel | None = None

    def connect_with_retry(self, retry_seconds: float = 2.0) -> MessageChannel:
        while True:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((self.host, self.port))
                channel = MessageChannel(sock)
                channel.send(make_register("server", self.server_id))
                self._log(f"Conectado al middleware {self.host}:{self.port} como servidor")
                return channel
            except OSError as exc:
                self._log(f"No se pudo conectar al middleware ({exc}); reintentando en {retry_seconds}s")
                time.sleep(retry_seconds)

    def run(self):
        self.channel = self.connect_with_retry()
        for msg in self.channel.recv():
            if msg.get("type") != "request":
                continue
            self._handle_request(msg)
        self._log("Conexión con el middleware cerrada. Fin del servidor.")

    def _handle_request(self, req: dict):
        request_id = req["request_id"]
        client_id = req["client_id"]
        op = req["op"]
        a = req["a"]
        b = req["b"]

        status, result, error = "ok", None, None
        try:
            result = compute(op, a, b)
        except ZeroDivisionError as exc:
            status, error = "error", str(exc)
        except (ValueError, TypeError) as exc:
            status, error = "error", str(exc)

        timestamp = now_iso()
        self.store.save(request_id, client_id, self.server_id, op, a, b, result, status, error, timestamp)

        if status == "ok":
            self._log(f"Procesado request {request_id} de '{client_id}': {a} {op} {b} = {result}")
        else:
            self._log(f"Error procesando request {request_id} de '{client_id}': {error}")

        result_msg = make_result(request_id, client_id, self.server_id, op, a, b, result, status, error)
        self.channel.send(result_msg)

    def _log(self, text: str):
        print(f"[server:{self.server_id}] {text}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Servidor de la calculadora distribuida")
    parser.add_argument("--id", required=True, help="Identificador único del servidor, ej. S1")
    parser.add_argument("--host", default="127.0.0.1", help="Host del middleware")
    parser.add_argument("--port", type=int, default=5000, help="Puerto del middleware")
    args = parser.parse_args()

    CalcServer(args.id, args.host, args.port).run()


if __name__ == "__main__":
    main()