"""Piezas falsas para probar la sincronización sin Bluetooth ni Oracle (equivalentes a las del servidor)."""

import asyncio
import queue
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from btsync.protocol import frame
from btsync.store import Catalog, EstadoCuenta

NOW = 1731170400000


class FakeStore:
    """Store en memoria: lo justo para que una Session real funcione, y espía de run_batch."""

    def notificar_sincronizacion(self, errores):
        pass

    def config(self):
        from btsync.config import DEFAULTS

        return dict(DEFAULTS)

    def __init__(self):
        self.rows, self.batch_calls = [], []

    def register_device(self, uuid, name): pass
    def sincronizar_cuenta(self, usuario, nombre, uuid): return EstadoCuenta("ACTIVO", "OPERADOR", None)
    def open_sync(self, uuid): return 1
    def close_sync(self, id, recibidos, aceptados): pass
    def last_seq(self, uuid): return len(self.rows)
    def catalog(self, usuario=None): return Catalog()
    def marcar_iniciada(self, usuario, id_tarea): pass
    def commit(self): pass
    def rollback(self): pass

    def insert_staging(self, uuid, seq, raw):
        self.rows.append((uuid, seq, raw))
        return True

    def run_batch(self, origen):
        self.batch_calls.append(origen)
        return (len(self.rows), 0)


class FakeConnection:
    """El test alimenta las líneas con ``feed``; ``cut`` simula que el teléfono se va."""

    def __init__(self):
        self._in, self.out = queue.Queue(), []

    def feed(self, *lines):
        for line in lines:
            self._in.put(line)

    def cut(self):
        self._in.put(None)

    def readline(self): return self._in.get(timeout=10)
    def write(self, data): self.out.append(data)
    def close(self): pass


class FakeTransport:
    def __init__(self, fail_with=None):
        self.fail_with = fail_with
        self.on_passkey = self.on_connection = None
        self.serving = False
        self.pairing_calls = self.serve_calls = self.stops = 0
        self.connections = []

    def begin_pairing(self, on_passkey):
        self.pairing_calls += 1
        if self.fail_with:
            raise self.fail_with
        self.on_passkey = on_passkey

    def serve(self, on_connection):
        self.serve_calls += 1
        self.on_connection, self.serving = on_connection, True

    def stop(self):
        self.stops += 1
        self.serving = False
        for conn in self.connections:
            conn.cut()

    def pair(self, code):
        """BlueZ pide confirmar un código; ``result`` se llena cuando el usuario decide."""
        result = {}
        thread = threading.Thread(
            target=lambda: result.update(accepted=asyncio.run(self.on_passkey(code))), daemon=True)
        thread.start()
        return thread, result

    def connect(self):
        conn = FakeConnection()
        self.connections.append(conn)
        threading.Thread(target=self.on_connection, args=(conn,), daemon=True).start()
        return conn


def hello(uuid="tst-gui"):
    return frame(["HELLO", "5", uuid, "Teléfono de prueba"])


def acct(usuario="tst-operador"):
    return frame(["ACCT", usuario, "Operador de prueba"])


def rec(seq, conteo="T-01", sku="A1", cant="1", operador="Ana"):
    return frame(["REC", str(seq), str(NOW + seq * 1000), conteo, sku, cant, operador, "", ""])


def end(n):
    return frame(["END", str(n)])


class FakeRunner:
    """``QueryRunner`` de mentira: ejecuta la función ya, en el hilo de la prueba, para probar flujos sin hilos.

    Misma firma que ``QueryRunner.run``; si la función falla, el mensaje va a ``on_error`` igual que el real.
    """

    def __init__(self) -> None:
        self.llamadas: list[tuple] = []

    def run(self, fn, on_done=None, on_error=None, *args, key=None, **kwargs):
        self.llamadas.append((fn, args, kwargs))
        try:
            resultado = fn(*args, **kwargs)
        except Exception as exc:  # igual que QueryWorker: el texto llega a la interfaz
            if on_error is not None:
                on_error(str(exc))
            return None
        if on_done is not None:
            on_done(resultado)
        return None


class FakeRemoto(QObject):
    """El servicio Bluetooth sin Oracle: la prueba pone el estado con ``poner`` y lee lo que pidió la vista."""

    status_changed = pyqtSignal(dict)
    listo = pyqtSignal()
    fallo = pyqtSignal(str)

    def __init__(self, **status):
        super().__init__()
        self._status = {"estado": "ESPERANDO_EMPAREJAMIENTO", "codigo": None, "recibidos": 0, "ultimo_error": None,
                        "desde": None, "listos": 0, "ultima": None, **status}
        self.pausas, self.reanudaciones, self.respuestas = [], [], []

    def status(self):
        return dict(self._status)

    def sondear(self):
        pass

    def poner(self, **cambios):
        self._status.update(cambios)
        self.status_changed.emit(self.status())

    def terminar_sync(self, recibidos, dispositivo="Teléfono de prueba"):
        from datetime import datetime

        from app.servicio import UltimaSync

        self.poner(estado="ESPERANDO_EMPAREJAMIENTO", recibidos=0, listos=self._status["listos"] + 1,
                   ultima=UltimaSync(datetime.now(), recibidos, dispositivo))
        self.listo.emit()

    def pausar(self, sesion):
        self.pausas.append(sesion.usuario)
        self.poner(estado="PAUSADO")

    def reanudar(self, sesion):
        self.reanudaciones.append(sesion.usuario)
        self.poner(estado="ESPERANDO_EMPAREJAMIENTO")

    def responder(self, sesion, aceptar):
        self.respuestas.append(aceptar)
