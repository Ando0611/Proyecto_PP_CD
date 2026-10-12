"""
Nodo del Campo de Datos - Calculadora Distribuida (arquitectura ADS)

Responsabilidad única: comunicación. Forma la malla con los otros nodos,
acepta conexiones de células (GUI y servidor) y retransmite por broadcast
todos los mensajes que recibe. No calcula operaciones.

- Acepta conexiones de nodos y de células por el mismo puerto. El primer
  mensaje de cada conexión indica el tipo de entidad ("nodo", "gui" o
  "servidor") y su id.
- Al arrancar se conecta a los nodos indicados en --vecinos.
- Cada mensaje recibido se reenvía a todas las conexiones activas, excepto
  a aquella por la que llegó.
- Prevención de ciclos: se guardan los ids de los mensajes ya procesados;
  si un mensaje llega otra vez, se descarta.
- Respuestas duplicadas: solo se retransmite la primera respuesta de cada
  solicitud; las demás se descartan.

Uso:
    python node.py --id N1 --port 6001
    python node.py --id N2 --port 6002 --vecinos 127.0.0.1:6001
"""

import argparse
import os
import socket
import sys
import threading
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.protocol import enviar, make_conexion, parse_direccion, recibir  # noqa: E402

MAX_IDS = 1000  # cuántos ids recientes recuerda el nodo


class Node:
    def __init__(self, node_id: str, port: int):
        self.node_id = node_id
        self.port = port
        self.lock = threading.Lock()
        # socket -> "entidad id" de cada conexión activa (nodos y células)
        self.conexiones: dict[socket.socket, str] = {}
        # registro temporal de ids de mensajes ya procesados
        self.vistos = deque(maxlen=MAX_IDS)
        # registro temporal de solicitudes que ya tienen respuesta
        self.respondidas = deque(maxlen=MAX_IDS)

    def start(self, vecinos: list):
        for direccion in vecinos:
            self._conectar_vecino(direccion)

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("0.0.0.0", self.port))
        listener.listen()
        self._log(f"Escuchando en el puerto {self.port}")
        while True:
            conn, _ = listener.accept()
            threading.Thread(target=self._aceptar, args=(conn,), daemon=True).start()

    # ------------------------------------------------------------------ #
    # Protocolo de conexión
    # ------------------------------------------------------------------ #
    def _conectar_vecino(self, direccion: str):
        try:
            sock = socket.create_connection(parse_direccion(direccion))
            enviar(sock, make_conexion("nodo", self.node_id))
        except OSError as exc:
            self._log(f"No se pudo conectar al nodo {direccion} ({exc})")
            return
        threading.Thread(target=self._atender, args=(sock,), daemon=True).start()

    def _aceptar(self, conn: socket.socket):
        enviar(conn, make_conexion("nodo", self.node_id, "conexion_ok"))
        self._atender(conn)

    def _atender(self, sock: socket.socket):
        nombre = None
        try:
            mensajes = recibir(sock)
            # El primer mensaje identifica a la entidad conectada
            primero = next(mensajes)
            nombre = f"{primero['entidad']} {primero['id']}"
            with self.lock:
                self.conexiones[sock] = nombre
                self._log(f"Conectado: {nombre} | conexiones activas: {sorted(self.conexiones.values())}")
            for msg in mensajes:
                self._broadcast(msg, sock)
        except (OSError, StopIteration, ValueError):
            pass
        finally:
            with self.lock:
                self.conexiones.pop(sock, None)
            sock.close()
            if nombre:
                self._log(f"Desconectado: {nombre}")

    # ------------------------------------------------------------------ #
    # Protocolo de comunicación (broadcast)
    # ------------------------------------------------------------------ #
    def _broadcast(self, msg: dict, origen: socket.socket):
        with self.lock:
            desde = self.conexiones[origen]
            resumen = f"{msg['codigo']} {msg['id'][:8]}"

            if msg["id"] in self.vistos:
                self._log(f"{resumen} de {desde}: ya procesado, se descarta")
                return
            self.vistos.append(msg["id"])

            if msg["codigo"].endswith("_RES"):
                if msg["id_solicitud"] in self.respondidas:
                    self._log(f"{resumen} de {desde}: la solicitud ya tiene respuesta, se descarta")
                    return
                self.respondidas.append(msg["id_solicitud"])

            destinos = [s for s in self.conexiones if s is not origen]
            self._log(f"{resumen} de {desde}: broadcast a {len(destinos)} conexiones")
            for sock in destinos:
                try:
                    enviar(sock, msg)
                except OSError:
                    pass

    def _log(self, text: str):
        print(f"[nodo:{self.node_id}] {text}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Nodo del Campo de Datos")
    parser.add_argument("--id", required=True, help="Identificador del nodo, ej. N1")
    parser.add_argument("--port", type=int, required=True, help="Puerto de escucha")
    parser.add_argument("--vecinos", nargs="*", default=[],
                        help="Direcciones host:puerto de los nodos ya iniciados")
    args = parser.parse_args()

    Node(args.id, args.port).start(args.vecinos)


if __name__ == "__main__":
    main()
