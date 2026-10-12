"""
Célula servidor - Calculadora Distribuida (arquitectura ADS)

Se configura con --servicio para atender una sola operación:
SUM (suma), SUB (resta), MUL (multiplicación) o DIV (división).

- Se conecta a un nodo del Campo de Datos y se identifica como "servidor".
- Recibe por broadcast todos los mensajes; solo atiende los que traen el
  Código de Contenido de solicitud de su servicio (ej. SUM_REQ).
- Calcula el resultado y envía una respuesta nueva con el Código de
  Contenido de respuesta (ej. SUM_RES) y el id de la solicitud original.

Uso:
    python server.py --servicio SUM --nodo 127.0.0.1:6001
"""

import argparse
import os
import socket
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.protocol import (  # noqa: E402
    SERVICIOS, compute, enviar, make_conexion, make_respuesta, nuevo_id, parse_direccion, recibir,
)


def main():
    parser = argparse.ArgumentParser(description="Célula servidor de la calculadora")
    parser.add_argument("--servicio", required=True, choices=list(SERVICIOS.values()))
    parser.add_argument("--nodo", required=True, help="Dirección host:puerto del nodo")
    args = parser.parse_args()

    cell_id = f"{args.servicio}-{nuevo_id()[:4]}"

    def log(text: str):
        print(f"[servidor:{cell_id}] {text}", flush=True)

    sock = socket.create_connection(parse_direccion(args.nodo))
    enviar(sock, make_conexion("servidor", cell_id))

    for msg in recibir(sock):
        if msg.get("tipo") == "conexion_ok":
            log(f"Conectado al nodo {msg['id']}")
            continue
        # Solo se atienden las solicitudes de este servicio
        if msg["codigo"] != args.servicio + "_REQ":
            continue
        resultado = compute(args.servicio, msg["a"], msg["b"])
        respuesta = make_respuesta(cell_id, msg, resultado)
        log(f"{msg['codigo']} {msg['id'][:8]} de {msg['origen']}: {msg['a']} y {msg['b']} "
            f"-> {respuesta['codigo']} {respuesta['id'][:8]} resultado {resultado}")
        enviar(sock, respuesta)

    log("Conexión con el nodo cerrada. Fin del servidor.")


if __name__ == "__main__":
    main()
