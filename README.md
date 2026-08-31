# Calculadora Distribuida — Cómputo Distribuido, Proyecto Primer Parcial

Aplicación distribuida cliente/servidor de **tres capas** (cliente pesado,
middleware, servidor) que implementa las cuatro operaciones aritméticas
básicas (suma, resta, multiplicación, división) usando **sockets TCP** como
mecanismo de comunicación.

## 1. Arquitectura

```
 Cliente 1 (GUI) ──┐                              ┌── Servidor 1
                    │                              │
 Cliente 2 (GUI) ───┼──── sockets ── MIDDLEWARE ───┼── Servidor 2
                    │      (TCP)                   │
 Cliente N (GUI) ──┘                              └── Servidor N
```

- **Cliente pesado** (`client/client.py`): aplicación de escritorio hecha con
  Tkinter (no es un navegador). Permite capturar una operación (A, operador,
  B), enviarla al middleware y ver los resultados que van llegando. No
  contiene lógica de negocio: nunca calcula la operación.
- **Middleware** (`middleware/middleware.py`): recibe conexiones de clientes
  y servidores por el mismo puerto TCP. El primer mensaje de cada conexión
  (`REGISTER`) le indica su rol, y así distingue conexiones de clientes de
  conexiones de servidores. Reenvía cada `REQUEST` de un cliente a **todos**
  los servidores conectados, y cada `RESULT` de un servidor a **todos** los
  clientes conectados. No tiene lógica de negocio ni persistencia propia.
- **Servidor** (`server/server.py`): recibe las solicitudes reenviadas por el
  middleware, calcula la operación, **persiste el resultado en SQLite**
  (`server/data/server_<id>.db`) y envía el resultado de vuelta al
  middleware.

El protocolo de mensajes (JSON delimitado por saltos de línea sobre TCP) está
documentado en `common/protocol.py`.

### Flujo obligatorio implementado

1. Un cliente genera una solicitud de operación aritmética.
2. El cliente la envía al middleware.
3. El middleware la reenvía a **todos** los servidores conectados.
4. Cada servidor procesa la operación.
5. Cada servidor envía su resultado al middleware.
6. El middleware reenvía **cada resultado recibido** a **todos** los
   clientes conectados (no solo al que originó la solicitud).
7. Cada cliente registra (persiste) la operación solicitada y los resultados
   recibidos.

Esto significa que, con 2 servidores conectados, cada solicitud produce 2
resultados (uno por servidor), y ambos resultados llegan a todos los
clientes conectados — así se demuestra en el video la redistribución del
middleware.

## 2. Persistencia

- **Servidor**: base SQLite `server/data/server_<id>.db`, tabla `results`
  con cada operación que procesó (request_id, cliente origen, operación,
  operandos, resultado, estado, error si aplica, timestamp).
- **Cliente**: base SQLite `client/data/client_<id>.db` con dos tablas:
  - `requests`: las operaciones que este cliente solicitó.
  - `results`: todos los resultados que este cliente recibió (de cualquier
    servidor, incluyendo solicitudes de otros clientes, ya que el
    middleware los distribuye a todos).

Puedes inspeccionar cualquier base con, por ejemplo:

```bash
sqlite3 server/data/server_S1.db "SELECT * FROM results;"
sqlite3 client/data/client_C1.db "SELECT * FROM requests;"
sqlite3 client/data/client_C1.db "SELECT * FROM results;"
```

## 3. Requisitos

- Python 3.9 o superior.
- Tkinter (incluido con Python en Windows/macOS; en Linux instalar el
  paquete del sistema si falta, p. ej. `sudo apt install python3-tk`).
- No se requieren dependencias externas (solo librería estándar: `socket`,
  `sqlite3`, `tkinter`, `json`, `threading`).

## 4. Cómo ejecutar la demostración completa

Abre una terminal por cada componente (para la evidencia mínima se piden al
menos 2 servidores y 2 clientes conectados simultáneamente, es decir, 5
terminales en total).

**Terminal 1 — Middleware:**

```bash
python middleware/middleware.py --host 0.0.0.0 --port 5000
```

**Terminal 2 — Servidor 1:**

```bash
python server/server.py --id S1 --host 127.0.0.1 --port 5000
```

**Terminal 3 — Servidor 2:**

```bash
python server/server.py --id S2 --host 127.0.0.1 --port 5000
```

**Terminal 4 — Cliente 1 (GUI):**

```bash
python client/client.py --id C1 --host 127.0.0.1 --port 5000
```

**Terminal 5 — Cliente 2 (GUI):**

```bash
python client/client.py --id C2 --host 127.0.0.1 --port 5000
```

Para correr los componentes en máquinas distintas de la misma red, usa la IP
real de la máquina donde corre el middleware en `--host` (y abre el puerto
5000 en el firewall si aplica).

### Qué mostrar en el video (según la evidencia mínima pedida)

1. Interfaz gráfica del cliente funcionando (Terminales 4 y 5).
2. Los 2 clientes y los 2 servidores conectados (revisar los logs del
   middleware, que imprime cada conexión y desconexión).
3. Enviar una operación desde un cliente (por ejemplo, Cliente 1: `8 / 2`).
4. Mostrar en los logs del middleware cómo la solicitud se reenvía a ambos
   servidores, y cómo ambos resultados se reenvían a ambos clientes.
5. Mostrar la tabla de resultados actualizándose en **ambos** clientes (no
   solo en el que envió la solicitud).
6. Probar las 4 operaciones, incluyendo un caso de división entre cero para
   mostrar el manejo de errores.
7. Abrir (con `sqlite3` o un visor de SQLite) las bases de datos del cliente
   y de un servidor para evidenciar la persistencia.

## 5. Prueba automatizada (sin GUI)

`tests/test_e2e.py` levanta el middleware, 2 servidores y 2 clientes
simulados (sockets crudos) para validar automáticamente el flujo completo,
el manejo de división entre cero y la persistencia en SQLite:

```bash
python tests/test_e2e.py
```

## 6. Estructura del proyecto

```
calculadora_distribuida/
├── common/
│   ├── __init__.py
│   └── protocol.py       # Mensajes JSON, framing por sockets, cálculo de operaciones
├── middleware/
│   └── middleware.py      # Enrutamiento/broadcast, sin lógica de negocio
├── server/
│   └── server.py          # Lógica de negocio + persistencia SQLite (server_<id>.db)
├── client/
│   └── client.py          # GUI Tkinter + persistencia SQLite (client_<id>.db)
├── tests/
│   └── test_e2e.py        # Prueba automatizada del flujo completo
└── README.md
```

## 7. Separación de responsabilidades

- El **cliente** solo construye y envía solicitudes, y muestra/persiste lo
  que recibe; nunca calcula el resultado.
- El **middleware** solo enruta y distribuye mensajes según el rol del
  emisor; nunca calcula ni persiste resultados.
- El **servidor** solo calcula operaciones y persiste sus propios
  resultados; no conoce a los clientes ni administra otras conexiones.

## 8. Pendiente para la entrega

Este repositorio cubre el código fuente y su prueba automatizada. Aún faltan
los otros dos entregables obligatorios del proyecto:

- **Reporte técnico** (arquitectura, componentes, flujo de comunicación,
  decisiones de diseño y persistencia).
- **Video con audio** demostrando la ejecución real (ver sección 4).
- **Liga al código fuente** (subir este proyecto a un repositorio, p. ej.
  GitHub, y compartir el enlace).
