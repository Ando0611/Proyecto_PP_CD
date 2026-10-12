# Calculadora Distribuida — Cómputo Distribuido, Proyecto Segundo Parcial

Adecuación de la calculadora del primer parcial a una **arquitectura ADS**:
un Campo de Datos formado por nodos en malla completa, células GUI y células
servidor, comunicación por **broadcast** y **Códigos de Contenido**.
Conserva las cuatro operaciones (suma, resta, multiplicación, división) y
usa **sockets TCP**.

## 1. Programas

- **Nodo del Campo de Datos** (`node/node.py`): forma la malla con los otros
  nodos, acepta conexiones de células y de nodos, y retransmite por
  broadcast todo mensaje que recibe. No calcula nada.
- **Célula servidor** (`server/server.py`): se configura con `--servicio`
  para atender una sola operación (`SUM`, `SUB`, `MUL` o `DIV`).
- **Célula cliente GUI** (`client/client.py`): interfaz Tkinter que captura
  los operandos y la operación, genera la solicitud y muestra la respuesta.

El mismo programa se usa para cualquier número de instancias; nada depende
de que sean cuatro nodos ni de un nodo central.

## 2. Protocolo de conexión

Todas las conexiones son sockets TCP con mensajes JSON de una línea.

- Lo primero que envía quien se conecta a un nodo es:
  `{"tipo": "conexion", "entidad": "nodo" | "gui" | "servidor", "id": "..."}`
- El nodo contesta `{"tipo": "conexion_ok", "entidad": "nodo", "id": "N1"}`.
- Cada nodo guarda sus conexiones activas (con el tipo de entidad y su id) y
  las imprime al conectarse o desconectarse alguien.
- La malla se forma con `--vecinos`: cada nodo nuevo se conecta a los nodos
  que ya están iniciados.

## 3. Mensajes y Códigos de Contenido

| Operación      | Código solicitud | Código respuesta |
|----------------|------------------|------------------|
| Suma           | `SUM_REQ`        | `SUM_RES`        |
| Resta          | `SUB_REQ`        | `SUB_RES`        |
| Multiplicación | `MUL_REQ`        | `MUL_RES`        |
| División       | `DIV_REQ`        | `DIV_RES`        |

Solicitud:

```json
{"id": "uuid", "codigo": "SUM_REQ", "a": 5.0, "b": 3.0, "origen": "GUI-1a2b"}
```

Respuesta (mensaje nuevo, con id propio y referencia a la solicitud):

```json
{"id": "uuid", "id_solicitud": "uuid", "codigo": "SUM_RES", "resultado": 8.0, "origen": "SUM-3c4d"}
```

## 4. Broadcast, ciclos y duplicados

- **Broadcast:** el nodo reenvía cada mensaje a todas sus conexiones (nodos
  y células) excepto a aquella por la que llegó.
- **Prevención de ciclos:** cada nodo guarda temporalmente los ids de los
  mensajes ya procesados (los últimos 1000). Si el mismo id llega otra vez,
  se descarta y no se retransmite.
- **Respuestas duplicadas:** como hay una célula servidor de cada operación
  en cada nodo, todas calculan la solicitud. Cada nodo guarda el id de las
  solicitudes que ya tienen respuesta y solo retransmite la **primera**
  respuesta de cada solicitud; las demás se descartan. Así cada GUI recibe
  una sola respuesta, y si una célula servidor falla responde otra.
- **Asociación solicitud-respuesta:** la GUI guarda el id de sus solicitudes
  y solo muestra la respuesta cuyo `id_solicitud` coincide.

## 5. Requisitos

- Python 3.9 o superior con Tkinter. Solo se usa la librería estándar.
- En macOS, si la ventana sale en negro, instalar Tk con
  `brew install python-tk`.

## 6. Cómo ejecutar la demostración

Todo se corre desde la carpeta del proyecto, en este orden: nodos, células
servidor y al final las GUI.

### 6.1 Los 4 nodos (una terminal por nodo, en este orden)

El orden importa: cada nodo se conecta a los que ya están corriendo.

```bash
python3 node/node.py --id N1 --port 6001
```

```bash
python3 node/node.py --id N2 --port 6002 --vecinos 127.0.0.1:6001
```

```bash
python3 node/node.py --id N3 --port 6003 --vecinos 127.0.0.1:6001 127.0.0.1:6002
```

```bash
python3 node/node.py --id N4 --port 6004 --vecinos 127.0.0.1:6001 127.0.0.1:6002 127.0.0.1:6003
```

### 6.2 Las 16 células servidor (una sola terminal)

Una de cada operación por nodo. Quedan en segundo plano y todas imprimen en
esa misma terminal.

```bash
for puerto in 6001 6002 6003 6004; do
  for servicio in SUM SUB MUL DIV; do
    python3 server/server.py --servicio $servicio --nodo 127.0.0.1:$puerto &
  done
done
```

### 6.3 Las 4 células GUI (una terminal por GUI)

```bash
python3 client/client.py --nodo 127.0.0.1:6001
```

```bash
python3 client/client.py --nodo 127.0.0.1:6002
```

```bash
python3 client/client.py --nodo 127.0.0.1:6003
```

```bash
python3 client/client.py --nodo 127.0.0.1:6004
```

En cada ventana se escriben los dos operandos, se elige la operación y se da
clic en "Enviar operación".

### 6.4 Para apagar todo

- Nodos y GUI: `Ctrl+C` en su terminal, o cerrar la ventana de la GUI.
- Células servidor: se cierran solas al apagar los nodos. Para cerrarlas
  antes: `pkill -f server/server.py`.
- Si un nodo dice que el puerto ya está en uso, quedó uno corriendo de
  antes: cerrarlo con `pkill -f node/node.py` y volver a empezar.

El recorrido de los mensajes se observa en la consola de cada nodo y de
cada célula servidor, y en la bitácora de cada GUI.

## 7. Estructura del proyecto

```
├── common/
│   └── protocol.py    # Mensajes JSON, Códigos de Contenido, cálculo de operaciones
├── node/
│   └── node.py        # Nodo del Campo de Datos (malla y broadcast)
├── server/
│   └── server.py      # Célula servidor (SUM, SUB, MUL o DIV)
├── client/
│   └── client.py      # Célula cliente GUI (Tkinter)
└── README.md
```
