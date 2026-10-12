"""
Protocolo de mensajes de la Calculadora Distribuida (arquitectura ADS).

Todas las conexiones son sockets TCP. Cada mensaje es un objeto JSON en una
sola línea, terminado con '\n'.

1) Mensaje de conexión (lo primero que se envía al conectarse a un nodo):
   {"tipo": "conexion", "entidad": "nodo" | "gui" | "servidor", "id": "N1"}

   El nodo contesta con su propia identificación:
   {"tipo": "conexion_ok", "entidad": "nodo", "id": "N2"}

2) Solicitud (GUI -> Campo de Datos):
   {
     "id": "uuid",              # identificador único del mensaje
     "codigo": "SUM_REQ",       # Código de Contenido
     "a": 5.0, "b": 3.0,        # operandos
     "origen": "GUI-1a2b"       # célula que originó el mensaje
   }

3) Respuesta (célula servidor -> Campo de Datos):
   {
     "id": "uuid",              # identificador propio de la respuesta
     "id_solicitud": "uuid",    # identificador de la solicitud original
     "codigo": "SUM_RES",       # Código de Contenido
     "resultado": 8.0,
     "origen": "SUM-3c4d"       # célula que originó el mensaje
   }
"""

import json
import uuid

# operación -> servicio (prefijo del Código de Contenido)
SERVICIOS = {"+": "SUM", "-": "SUB", "*": "MUL", "/": "DIV"}


def nuevo_id() -> str:
    return str(uuid.uuid4())


def make_conexion(entidad: str, entidad_id: str, tipo: str = "conexion") -> dict:
    return {"tipo": tipo, "entidad": entidad, "id": entidad_id}


def make_solicitud(origen: str, op: str, a: float, b: float) -> dict:
    return {
        "id": nuevo_id(),
        "codigo": SERVICIOS[op] + "_REQ",
        "a": a,
        "b": b,
        "origen": origen,
    }


def make_respuesta(origen: str, solicitud: dict, resultado) -> dict:
    return {
        "id": nuevo_id(),
        "id_solicitud": solicitud["id"],
        "codigo": solicitud["codigo"].replace("_REQ", "_RES"),
        "resultado": resultado,
        "origen": origen,
    }


def compute(servicio: str, a: float, b: float):
    """Ejecuta la operación aritmética del servicio indicado."""
    if servicio == "SUM":
        return a + b
    if servicio == "SUB":
        return a - b
    if servicio == "MUL":
        return a * b
    if b == 0:
        return "Error: división entre cero"
    return a / b


def enviar(sock, msg: dict) -> None:
    sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))


def recibir(sock):
    """Generador que produce los mensajes JSON que van llegando por el socket."""
    for linea in sock.makefile("r", encoding="utf-8"):
        yield json.loads(linea)


def parse_direccion(texto: str):
    """Convierte 'host:puerto' en (host, puerto)."""
    host, puerto = texto.split(":")
    return host, int(puerto)
