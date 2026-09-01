"""
Prueba end-to-end (sin GUI) del flujo obligatorio descrito en las instrucciones:

1. Levanta el middleware en un puerto libre.
2. Levanta 2 servidores (S1, S2) reales (procesos separados, cada uno con su
   propia base SQLite).
3. Simula 2 clientes (C1, C2) usando sockets crudos (misma librería
   common.protocol que usa la GUI real), para no depender de un display.
4. Verifica que:
   - Una solicitud de un cliente llega a AMBOS servidores.
   - Los resultados de AMBOS servidores llegan a AMBOS clientes.
   - Las 4 operaciones (+, -, *, /) funcionan, incluida división por cero
     como caso de error controlado.
   - Los datos quedan persistidos en las bases SQLite de cliente y servidor.
"""

import os
import socket
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.protocol import MessageChannel, make_register, make_request  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 5999


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_port(host, port, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def raw_client(client_id, host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    ch = MessageChannel(sock)
    ch.send(make_register("client", client_id))
    return ch


def main():
    port = free_port()
    procs = []
    for db in ("server/data", "client/data"):
        d = os.path.join(ROOT, db)
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.startswith("server_test_") or f.startswith("client_test_"):
                    os.remove(os.path.join(d, f))

    print(f"== Iniciando middleware en puerto {port} ==")
    mw = subprocess.Popen(
        [sys.executable, "middleware/middleware.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
    )
    procs.append(mw)
    assert wait_port("127.0.0.1", port), "El middleware no levantó a tiempo"

    print("== Iniciando 2 servidores (S1_test, S2_test) ==")
    for sid in ("S1_test", "S2_test"):
        p = subprocess.Popen(
            [sys.executable, "server/server.py", "--id", sid, "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT,
        )
        procs.append(p)
    time.sleep(1.0)  # dar tiempo a que ambos servidores se registren

    print("== Conectando 2 clientes simulados (C1_test, C2_test) ==")
    c1 = raw_client("C1_test", "127.0.0.1", port)
    c2 = raw_client("C2_test", "127.0.0.1", port)
    time.sleep(0.3)

    gens = {"C1_test": c1.recv(), "C2_test": c2.recv()}

    operations = [("+", 5, 3), ("-", 10, 4), ("*", 6, 7), ("/", 9, 3), ("/", 8, 0)]
    sent_ids = []

    for op, a, b in operations:
        req = make_request("C1_test", op, a, b)
        sent_ids.append(req["request_id"])
        c1.send(req)
        time.sleep(0.2)

    print("== Recolectando resultados recibidos por cada cliente ==")
    received = {"C1_test": [], "C2_test": []}
    deadline = time.time() + 8
    expected_count = len(operations) * 2  # 2 servidores por cada request
    while time.time() < deadline and (
        len(received["C1_test"]) < expected_count or len(received["C2_test"]) < expected_count
    ):
        for cid, gen in gens.items():
            c1.sock.settimeout(0.2)
            c2.sock.settimeout(0.2)
            try:
                msg = next(gen)
            except socket.timeout:
                continue
            except StopIteration:
                continue
            if msg and msg.get("type") == "result":
                received[cid].append(msg)

    ok = True

    for cid in ("C1_test", "C2_test"):
        n = len(received[cid])
        print(f"Cliente {cid} recibió {n} resultados (esperados: {expected_count})")
        if n != expected_count:
            ok = False

    servers_seen = {r["server_id"] for r in received["C1_test"]}
    print(f"Servidores que respondieron (vistos por C1_test): {servers_seen}")
    if servers_seen != {"S1_test", "S2_test"}:
        ok = False

    ids_seen = {r["request_id"] for r in received["C1_test"]}
    if not set(sent_ids).issubset(ids_seen):
        print("ERROR: no todos los request_id enviados fueron respondidos")
        ok = False

    div0_results = [r for r in received["C1_test"] if r["op"] == "/" and r["b"] == 0]
    if not div0_results or any(r["status"] != "error" for r in div0_results):
        print("ERROR: la división entre cero no se manejó como error")
        ok = False
    else:
        print(f"División entre cero manejada correctamente: {div0_results[0]['error']}")

    print("== Verificando persistencia en SQLite de los servidores ==")
    for sid in ("S1_test", "S2_test"):
        db_path = os.path.join(ROOT, "server", "data", f"server_{sid}.db")
        if not os.path.exists(db_path):
            print(f"ERROR: no existe {db_path}")
            ok = False
            continue
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
        print(f"{sid}: {count} registros persistidos")
        if count != len(operations):
            ok = False
        conn.close()

    c1.close()
    c2.close()
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()

    print("\n== RESULTADO FINAL:", "OK" if ok else "FALLÓ", "==")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
