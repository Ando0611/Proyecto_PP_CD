"""
Protocolo de mensajería para la Calculadora Distribuida.

Arquitectura cliente / middleware / servidor de tres capas.
Todas las conexiones son TCP sockets. Cada mensaje es un objeto JSON
serializado en una sola línea, terminado con '\n' (newline-delimited JSON).
Esto evita el problema de "framing" de TCP (los mensajes pueden llegar
fragmentados o concatenados).

Tipos de mensaje:

1) REGISTER  (cliente/servidor -> middleware)
   {
     "type": "register",
     "role": "client" | "server",
     "id": "C1"            # identificador propio, elegido por el proceso
   }

2) REGISTER_OK (middleware -> cliente/servidor)
   {
     "type": "register_ok",
     "id": "C1",
     "role": "client"
   }

3) REQUEST  (cliente -> middleware -> todos los servidores)
   {
     "type": "request",
     "request_id": "uuid",
     "client_id": "C1",
     "op": "+", "-", "*", "/",
     "a": 5.0,
     "b": 3.0,
     "timestamp": "2026-08-31T12:00:00"
   }

4) RESULT   (servidor -> middleware -> todos los clientes)
   {
     "type": "result",
     "request_id": "uuid",
     "client_id": "C1",       # cliente que originó la solicitud
     "server_id": "S1",       # servidor que la procesó
     "op": "+",
     "a": 5.0,
     "b": 3.0,
     "result": 8.0,           # null si status == "error"
     "status": "ok" | "error",
     "error": null | "mensaje de error",
     "timestamp": "2026-08-31T12:00:01"
   }

5) INFO / LOG (middleware -> todos, opcional, solo informativo)
   {
     "type": "info",
     "message": "..."
   }
"""

import json
import socket
import threading
import uuid
from datetime import datetime, timezone

ENCODING = "utf-8"
OPERATIONS = ("+", "-", "*", "/")


def now_iso() -> str:
    """Marca de tiempo ISO-8601 en UTC, legible y ordenable."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_request_id() -> str:
    return str(uuid.uuid4())


def make_register(role: str, node_id: str) -> dict:
    assert role in ("client", "server")
    return {"type": "register", "role": role, "id": node_id}


def make_register_ok(node_id: str, role: str) -> dict:
    return {"type": "register_ok", "id": node_id, "role": role}


def make_request(client_id: str, op: str, a: float, b: float, request_id: str = None) -> dict:
    assert op in OPERATIONS
    return {
        "type": "request",
        "request_id": request_id or new_request_id(),
        "client_id": client_id,
        "op": op,
        "a": a,
        "b": b,
        "timestamp": now_iso(),
    }


def make_result(request_id: str, client_id: str, server_id: str, op: str, a: float, b: float,
                 result=None, status: str = "ok", error: str = None) -> dict:
    return {
        "type": "result",
        "request_id": request_id,
        "client_id": client_id,
        "server_id": server_id,
        "op": op,
        "a": a,
        "b": b,
        "result": result,
        "status": status,
        "error": error,
        "timestamp": now_iso(),
    }


def make_info(message: str) -> dict:
    return {"type": "info", "message": message}


def compute(op: str, a: float, b: float):
    """Ejecuta la operación aritmética. Lanza ZeroDivisionError o ValueError."""
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            raise ZeroDivisionError("División entre cero no permitida")
        return a / b
    raise ValueError(f"Operación no soportada: {op}")


class MessageChannel:
    """
    Envuelve un socket TCP y ofrece envío/recepción de mensajes JSON
    delimitados por saltos de línea, de forma segura entre hilos para el
    envío (un lock por canal).
    """

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._send_lock = threading.Lock()
        self._recv_buffer = b""

    def send(self, obj: dict) -> None:
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode(ENCODING)
        with self._send_lock:
            self.sock.sendall(data)

    def recv(self):
        """
        Generador que produce diccionarios JSON conforme van llegando
        mensajes completos (terminados en '\n') por el socket.
        Termina (StopIteration) cuando la conexión se cierra.
        """
        while True:
            while b"\n" not in self._recv_buffer:
                chunk = self.sock.recv(4096)
                if not chunk:
                    return  # conexión cerrada
                self._recv_buffer += chunk
            line, self._recv_buffer = self._recv_buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                yield json.loads(line.decode(ENCODING))
            except json.JSONDecodeError:
                # Mensaje corrupto: se ignora y se continúa escuchando.
                continue

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
