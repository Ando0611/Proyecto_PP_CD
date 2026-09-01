"""
Middleware - Calculadora Distribuida (Cómputo Distribuido, Proyecto Primer Parcial)

Responsabilidad única: comunicación y distribución de mensajes.
NO contiene lógica de negocio (no resuelve operaciones) ni persistencia.

- Acepta conexiones TCP de clientes y de servidores por el mismo puerto.
- El primer mensaje de cada conexión debe ser un REGISTER que indica el rol
  ("client" o "server") y un id. Con eso el middleware clasifica la conexión.
- Cuando un cliente envía un REQUEST, el middleware lo reenvía a TODOS los
  servidores conectados.
- Cuando un servidor envía un RESULT, el middleware lo reenvía a TODOS los
  clientes conectados.
- Soporta múltiples clientes y múltiples servidores concurrentes (un hilo
  por conexión).

Uso:
    python middleware.py [--host 0.0.0.0] [--port 5000]
"""

import argparse
import os
import socket
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.protocol import MessageChannel, make_info  # noqa: E402


class Middleware:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.lock = threading.Lock()
        # id -> {"channel": MessageChannel, "role": "client"/"server"}
        self.clients: dict[str, MessageChannel] = {}
        self.servers: dict[str, MessageChannel] = {}

    # ------------------------------------------------------------------ #
    # Ciclo de vida del servidor de sockets
    # ------------------------------------------------------------------ #
    def start(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, self.port))
        listener.listen(50)
        self._log(f"Middleware escuchando en {self.host}:{self.port}")
        try:
            while True:
                conn, addr = listener.accept()
                threading.Thread(
                    target=self._handle_connection, args=(conn, addr), daemon=True
                ).start()
        except KeyboardInterrupt:
            self._log("Apagando middleware...")
        finally:
            listener.close()

    # ------------------------------------------------------------------ #
    # Manejo de una conexión (cliente o servidor)
    # ------------------------------------------------------------------ #
    def _handle_connection(self, conn: socket.socket, addr):
        channel = MessageChannel(conn)
        node_id = None
        role = None
        try:
            messages = channel.recv()

            # 1. Primer mensaje obligatorio: REGISTER
            first = next(messages, None)
            if not first or first.get("type") != "register":
                self._log(f"Conexión {addr} rechazada: no envió REGISTER")
                channel.close()
                return

            role = first.get("role")
            node_id = first.get("id") or f"{role}-{addr[1]}"
            if role not in ("client", "server"):
                self._log(f"Conexión {addr} rechazada: rol inválido '{role}'")
                channel.close()
                return

            self._register(role, node_id, channel)
            self._log(f"{role.upper()} '{node_id}' conectado desde {addr}")

            # 2. Bucle principal: distribuir mensajes según el rol de origen
            for msg in messages:
                mtype = msg.get("type")
                if role == "client" and mtype == "request":
                    self._log(
                        f"REQUEST de cliente '{node_id}' "
                        f"({msg.get('a')} {msg.get('op')} {msg.get('b')}) "
                        f"-> reenviando a {len(self.servers)} servidor(es)"
                    )
                    self._broadcast(self.servers, msg)
                elif role == "server" and mtype == "result":
                    self._log(
                        f"RESULT de servidor '{node_id}' para request "
                        f"{msg.get('request_id')} -> reenviando a {len(self.clients)} cliente(s)"
                    )
                    self._broadcast(self.clients, msg)
                else:
                    self._log(f"Mensaje ignorado de '{node_id}' (tipo={mtype}, rol={role})")
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
        finally:
            self._unregister(role, node_id)
            channel.close()
            if node_id:
                self._log(f"{(role or '?').upper()} '{node_id}' desconectado")

    # ------------------------------------------------------------------ #
    # Registro / baja de nodos
    # ------------------------------------------------------------------ #
    def _register(self, role: str, node_id: str, channel: MessageChannel):
        with self.lock:
            registry = self.clients if role == "client" else self.servers
            registry[node_id] = channel

    def _unregister(self, role: str, node_id: str):
        if not role or not node_id:
            return
        with self.lock:
            registry = self.clients if role == "client" else self.servers
            registry.pop(node_id, None)

    # ------------------------------------------------------------------ #
    # Difusión (broadcast) de mensajes
    # ------------------------------------------------------------------ #
    def _broadcast(self, registry: dict, msg: dict):
        with self.lock:
            targets = list(registry.items())
        for node_id, channel in targets:
            try:
                channel.send(msg)
            except OSError:
                self._log(f"No se pudo enviar a '{node_id}', probablemente desconectado")

    @staticmethod
    def _log(text: str):
        print(f"[middleware] {text}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Middleware de la calculadora distribuida")
    parser.add_argument("--host", default="0.0.0.0", help="Interfaz de escucha")
    parser.add_argument("--port", type=int, default=5000, help="Puerto de escucha")
    args = parser.parse_args()

    Middleware(args.host, args.port).start()


if __name__ == "__main__":
    main()