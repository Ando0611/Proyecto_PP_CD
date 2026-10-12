"""
Célula cliente (GUI) - Calculadora Distribuida (arquitectura ADS)

Aplicación de escritorio hecha con Tkinter. Captura los operandos y la
operación, genera la solicitud con su Código de Contenido, la envía al nodo
al que está conectada y muestra la respuesta cuando llega.

No calcula la operación: solo la solicita y muestra lo que respondió una
célula servidor.

Uso:
    python client.py --nodo 127.0.0.1:6001
"""

import argparse
import os
import queue
import socket
import sys
import threading

# Silencia el aviso de Tk obsoleto en el Python del sistema en macOS.
os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

import tkinter as tk  # noqa: E402
from tkinter import messagebox, ttk  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.protocol import (  # noqa: E402
    SERVICIOS, enviar, make_conexion, make_solicitud, nuevo_id, parse_direccion, recibir,
)


class ClientApp(tk.Tk):
    def __init__(self, nodo: str):
        super().__init__()
        self.cell_id = f"GUI-{nuevo_id()[:4]}"
        self.title(f"Calculadora ADS - {self.cell_id}")
        self.geometry("620x420")

        # id de solicitud -> texto de la operación, para asociar la respuesta
        self.pendientes: dict[str, str] = {}
        self.inbox: queue.Queue = queue.Queue()

        self._build_widgets()

        self.sock = socket.create_connection(parse_direccion(nodo))
        enviar(self.sock, make_conexion("gui", self.cell_id))
        threading.Thread(target=self._recibir, daemon=True).start()
        self.after(100, self._poll_inbox)

    def _build_widgets(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        self.status_var = tk.StringVar(value="Conectando...")
        ttk.Label(top, textvariable=self.status_var).grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 8))

        ttk.Label(top, text="Operando A:").grid(row=1, column=0, sticky="w")
        self.entry_a = ttk.Entry(top, width=12)
        self.entry_a.grid(row=1, column=1, padx=5)

        ttk.Label(top, text="Operación:").grid(row=1, column=2, sticky="w")
        self.op_var = tk.StringVar(value="+")
        ttk.Combobox(
            top, textvariable=self.op_var, values=list(SERVICIOS), width=4, state="readonly"
        ).grid(row=1, column=3, padx=5)

        ttk.Label(top, text="Operando B:").grid(row=1, column=4, sticky="w")
        self.entry_b = ttk.Entry(top, width=12)
        self.entry_b.grid(row=1, column=5, padx=5)

        ttk.Button(top, text="Enviar operación", command=self._on_send).grid(
            row=2, column=0, columnspan=6, pady=10, sticky="w"
        )

        self.result_var = tk.StringVar(value="Resultado:")
        ttk.Label(top, textvariable=self.result_var, font=("TkDefaultFont", 14, "bold")).grid(
            row=3, column=0, columnspan=6, sticky="w"
        )

        # Bitácora de mensajes enviados y recibidos
        self.bitacora = tk.Listbox(self)
        self.bitacora.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _log(self, text: str):
        print(f"[gui:{self.cell_id}] {text}", flush=True)
        self.bitacora.insert(0, text)

    def _on_send(self):
        try:
            a = float(self.entry_a.get())
            b = float(self.entry_b.get())
        except ValueError:
            messagebox.showerror("Datos inválidos", "Los operandos deben ser números.")
            return

        op = self.op_var.get()
        solicitud = make_solicitud(self.cell_id, op, a, b)
        self.pendientes[solicitud["id"]] = f"{a} {op} {b}"
        try:
            enviar(self.sock, solicitud)
        except OSError as exc:
            messagebox.showerror("Sin conexión", str(exc))
            return
        self._log(f"Enviada {solicitud['codigo']} {solicitud['id'][:8]}: {a} {op} {b}")

    # La red se lee en un hilo aparte; la GUI procesa los mensajes con after()
    def _recibir(self):
        try:
            for msg in recibir(self.sock):
                self.inbox.put(msg)
        except OSError:
            pass
        self.inbox.put({"tipo": "desconectado"})

    def _poll_inbox(self):
        try:
            while True:
                self._handle_message(self.inbox.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._poll_inbox)

    def _handle_message(self, msg: dict):
        if msg.get("tipo") == "conexion_ok":
            self.status_var.set(f"Célula {self.cell_id} conectada al nodo {msg['id']}")
            return
        if msg.get("tipo") == "desconectado":
            self.status_var.set("Desconectado del nodo")
            return

        # Solo interesan las respuestas a solicitudes hechas por esta GUI
        if not msg["codigo"].endswith("_RES"):
            return
        operacion = self.pendientes.pop(msg["id_solicitud"], None)
        if operacion is None:
            return
        self.result_var.set(f"Resultado: {operacion} = {msg['resultado']}")
        self._log(
            f"Recibida {msg['codigo']} {msg['id'][:8]} de {msg['origen']} "
            f"para la solicitud {msg['id_solicitud'][:8]}: {operacion} = {msg['resultado']}"
        )


def main():
    parser = argparse.ArgumentParser(description="Célula cliente (GUI) de la calculadora")
    parser.add_argument("--nodo", required=True, help="Dirección host:puerto del nodo")
    args = parser.parse_args()

    ClientApp(args.nodo).mainloop()


if __name__ == "__main__":
    main()
