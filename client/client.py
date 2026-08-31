"""
Aplicación de escritorio construida con Tkinter. 
Responsabilidad : Capturar la operación que pude el usuario, 
enviarla al middleware, mostrar los resultados que van llegando y 
persistir localmente tanto las solicitudes hechas como los resultados recibidos.
"""

import argparse
import os 
import queue
import socket
import sqlite3
import sys 
import threading
import tkinter as tk
from tkinter import messagebox, ttk

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.protocol import MessageChannel, make_register, make_request, now_iso

DB_DIR = os.path.join(os.path.dirname(__file__), "data")

# ------------------------------------------------
# Persistenia local del cliente
# ------------------------------------------------

class ClientStore:
    """
    Persiste tanto las operaciones solicitadas por este cliente como los resultados recibidos.
    """

    def __init__(self, client_id: str):
        os.makedirs(DB_DIR, exist_ok=True)
        self.path = os.path.join(DB_DIR, f"client_{client_id}.db")
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
            request_id TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            op TEXT NOT NULL,
            a REAL NOT NULL,
            b REAL NOT NULL,
            timestamp TEXT NOT NULL,
            own INTEGER NOT NULL DEFAULT 1
            )           
            """
        )
        self._conn.execute (
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

    def save_request(self, request_id, client_id, op, a, b,timestamp, own=True):
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO requests (request_id, client_id, op, a, b, 
                    timestamp, own)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, 
                (request_id, client_id, op, a, b, timestamp, 1 if own else 0),
            )
            self._conn.commit()

    def save_result(self, request_id, client_id, server_id, op, a, b, result, status, error, timestamp):
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO results
                    (request_id, client_id, server_id, op, a, b, result, status, error, timestamp)
                VALUES (?, ?, ? , ? , ?, ?, ?, ?, ?, ?)
                """, 
                (request_id, client_id, server_id, op, a, b, result, status, error, timestamp),
            )
            self._conn.commit()

    def fetch_history(self, limit=200):
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT r.timestamp, r.request_id, r.client_id, r.server_id, r.op, r.a, r.b, r.result, r.status, r.error
                FROM results r
                ORDER BY r.id DESC
                LIMIT ?
                """
                (limit,),
            )
            return cur.fetchall()
        

# -------------------------------------------------------
# Comunicación de red usando un hilo aparte.
# -------------------------------------------------------

class NetworkClient:
    """
    Maneja la conexión socket con el middleware en un hilo propio y coloca
    los mensajes recibidios en una cola para que la GUI los procese
    de forma segura con root.after().
    """

    def __init__(self, client_id: str, host:str, port:int, inbox: queue.Queue):
        self.client_id = client_id
        self.host = host
        self.port = port
        self.inbox = inbox
        self.channel: MessageChannel | None = None
        self.connected = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try: 
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.host, self.port))
            self.channel = MessageChannel(sock)
            self.channel.send(make_register("client", self.client_id))
            self.connected.set()
            self.inbox.put({"_local": "connected"})
            for msg in self.channel.recv():
                self.inbox.put(msg)
        except OSError as exc:        
            self.inbox.put({"_local": "error", "message": str(exc)})

    def send_request(self, req: dict):
        if not self.channel:
            raise ConnectionError("No hay conexión con el middleware")
        self.channel.send(req)


# ------------------------------
# Interfaz gráfica
# ------------------------------

class ClientApp(tk.Tk):
    OPS = ["+", "-", "*", "/"]

    def __init__(self, client_id: str, host:str, port:int):
        super().__init__()
        self.client_id = client_id
        self.title(f"Calculadora Distribuida - Cliente {client_id}")
        self.geometry("760x520")
        self.minsize(680, 460)

        self.store = ClientStore(client_id)
        self.inbox: queue.Queue = queue.Queue()
        self.net = NetworkClient(client_id, host, port, self.inbox)

        self._build_widgets(host, port)
        self._load_history_from_db()

        self.net.start()
        self.after(100, self._poll_inbox)

    # ------------------------------------------------------------------------ #

    def _build_widget(self, host, port):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text=f"Cliente: {self.client_id}", font=("TkDefaultFont", 11, "bold")).grid(
            row=0, column=0, columnspan=6, sticky="w"
        )
        self.status_var = tk.StringVar(value=f"Conectando a {host}:{port} ...")
        ttk.Label(top, textvariable=self.status_var, foreground="#a05a00").grid(
            row=1, column=0, columnspan=6, sticky="w", pady=(0, 8)
        )

        ttk.Label(top, text="Operando A:").grid(row=2, column=0, sticky="w")
        self.entry_a = ttk.Entry(top, width=12)
        self.entry_a.grid(row=2, column=1, padx=5)

        ttk.Label(top, text="Operación:").grid(row=2, column=2, sticky="w")
        self.op_var = tk.StringVar(value="+")
        op_combo = ttk.Combobox(
            top, textvariable=self.op_var, values=self.OPS, width=4, state="readonly"
        )
        op_combo.grid(row=2, column=3, padx=5)

        ttk.Label(top, text="Operando B:").grid(row=2, column=4, sticky="w")
        self.entry_b = ttk.Entry(top, width=12)
        self.entry_b.grid(row=2, column=5, padx=5)

        self.send_btn = ttk.Button(top, text="Enviar operación", command=self._on_send)
        self.send_btn.grid(row=3, column=0, columnspan=6, pady=10, sticky="w")

        # Tabla de resultados
        columns = ("timestamp", "request_id", "client_id", "server_id", "operacion", "resultado", "estado")
        headers = {
            "timestamp": "Hora",
            "request_id": "Request ID",
            "client_id": "Cliente origen",
            "server_id": "Servidor",
            "operacion": "Operación",
            "resultado": "Resultado",
            "estado": "Estado",
        }
        widths = {
            "timestamp": 150,
            "request_id": 90,
            "client_id": 90,
            "server_id": 80,
            "operacion": 130,
            "resultado": 90,
            "estado": 70,
        }

        table_frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        table_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=16)
        for col in columns:
            self.tree.heading(col, text=headers[col])
            self.tree.column(col, width=widths[col], anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        footer = ttk.Frame(self, padding=(10, 0, 10, 10))
        footer.pack(fill="x")
        ttk.Label(
            footer,
            text=(
                "Nota: cada solicitud se reenvía a todos los servidores conectados y cada "
                "resultado se distribuye a todos los clientes conectados (incluye solicitudes "
                "de otros clientes)."
            ),
            wraplength=720,
            foreground="#555555",
        ).pack(anchor="w")

    # ------------------------------------------------------------------ #
    def _load_history_from_db(self):
        for row in reversed(self.store.fetch_history()):
            self._insert_row(row)

    def _insert_row(self, row):
        timestamp, request_id, client_id, server_id, op, a, b, result, status, error = row
        op_text = f"{a} {op} {b}"
        result_text = "ERROR" if status == "error" else result
        tag = "error" if status == "error" else ("mine" if client_id == self.client_id else "")
        self.tree.insert(
            "",
            0,
            values=(timestamp, request_id[:8], client_id, server_id, op_text, result_text, status),
            tags=(tag,) if tag else (),
        )
        self.tree.tag_configure("error", foreground="#b00020")
        self.tree.tag_configure("mine", font=("TkDefaultFont", 10, "bold"))

    # ------------------------------------------------------------------ #
    def _on_send(self):
        a_text, b_text = self.entry_a.get().strip(), self.entry_b.get().strip()
        try:
            a = float(a_text)
            b = float(b_text)
        except ValueError:
            messagebox.showerror("Datos inválidos", "Los operandos deben ser números.")
            return

        op = self.op_var.get()
        req = make_request(self.client_id, op, a, b)

        try:
            self.net.send_request(req)
        except ConnectionError as exc:
            messagebox.showerror("Sin conexión", str(exc))
            return

        # El cliente persiste la operación que solicitó, tal como pide el enunciado.
        self.store.save_request(req["request_id"], self.client_id, op, a, b, req["timestamp"], own=True)
        self.status_var.set(f"Solicitud enviada: {a} {op} {b}  (request {req['request_id'][:8]})")

    # ------------------------------------------------------------------ #
    def _poll_inbox(self):
        try:
            while True:
                msg = self.inbox.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_inbox)

    def _handle_message(self, msg: dict):
        if msg.get("_local") == "connected":
            self.status_var.set("Conectado al middleware")
            return
        if msg.get("_local") == "disconnected":
            self.status_var.set("Desconectado del middleware")
            return
        if msg.get("_local") == "error":
            self.status_var.set(f"Error de conexión: {msg.get('message')}")
            return

        if msg.get("type") == "result":
            self.store.save_result(
                msg["request_id"], msg["client_id"], msg["server_id"], msg["op"],
                msg["a"], msg["b"], msg.get("result"), msg["status"], msg.get("error"), msg["timestamp"],
            )
            row = (
                msg["timestamp"], msg["request_id"], msg["client_id"], msg["server_id"],
                msg["op"], msg["a"], msg["b"], msg.get("result"), msg["status"], msg.get("error"),
            )
            self._insert_row(row)


def main():
    parser = argparse.ArgumentParser(description="Cliente GUI de la calculadora distribuida")
    parser.add_argument("--id", required=True, help="Identificador único del cliente, ej. C1")
    parser.add_argument("--host", default="127.0.0.1", help="Host del middleware")
    parser.add_argument("--port", type=int, default=5000, help="Puerto del middleware")
    args = parser.parse_args()

    app = ClientApp(args.id, args.host, args.port)
    app.mainloop()


if __name__ == "__main__":
    main()

    