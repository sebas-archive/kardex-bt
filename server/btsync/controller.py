"""Controlador de la sincronización: el "disparador" que usa la aplicación de escritorio.

Vive en el mismo proceso que la GUI (sin HTTP). ``start()`` hace visible el PC durante
``discoverable_s`` segundos; cuando un teléfono se conecta corre una ``Session`` y, al terminar,
ejecuta el batch (D9: el batch corre fuera de la sesión). Una sola sincronización a la vez (D19).

Estados::

    IDLE ──start──▶ ESPERANDO_EMPAREJAMIENTO ◀──confirm(True)── CONFIRMAR_CODIGO
                      │      ▲   └──────código de BlueZ──────────▶   │
                      │      └── corte (el teléfono reintenta)       └─ confirm(False) ─▶ IDLE
                  conexión
                      ▼
                  CONECTADO ─HELLO─▶ RECIBIENDO ─END/BYE─▶ PROCESANDO ─batch─▶ LISTO | ERROR

Sin conexión al vencer el plazo, o con ``cancel()``, se vuelve a IDLE y el PC deja de aceptar.
Todo el trabajo ocurre en hilos propios; ``on_change(status)`` se llama en cada transición (y en
cada avance de ``recibidos``) desde esos hilos: la GUI debe convertirlo en una señal.
"""

from __future__ import annotations

import asyncio
import logging
import math
import sys
import threading
import time
from typing import Callable

from .session import Session
from .store import Store
from .transports.base import BluetoothUnavailable, Connection, Transport

IDLE = "IDLE"
ESPERANDO_EMPAREJAMIENTO = "ESPERANDO_EMPAREJAMIENTO"
CONFIRMAR_CODIGO = "CONFIRMAR_CODIGO"
CONECTADO = "CONECTADO"
RECIBIENDO = "RECIBIENDO"
PROCESANDO = "PROCESANDO"
LISTO = "LISTO"
ERROR = "ERROR"

_VISIBLE = (ESPERANDO_EMPAREJAMIENTO, CONFIRMAR_CODIGO)  # corre la cuenta regresiva
_REPOSO = (IDLE, LISTO, ERROR)                            # no hay ciclo en marcha


class SyncController:
    def __init__(
        self,
        transport: Transport,
        store: Store,
        on_change: Callable[[dict], None],
        discoverable_s: int = 120,
    ) -> None:
        self.transport = transport
        self.store = store
        self._on_change = on_change
        self._discoverable_s = discoverable_s
        self._lock = threading.RLock()            # protege el estado
        self._transport_lock = threading.Lock()   # serializa abrir/parar el transporte
        self._gen = 0                             # cambia en cada ciclo: invalida hilos viejos
        self._estado = IDLE
        self._codigo: str | None = None
        self._recibidos = 0
        self._ultimo_error: str | None = None
        self._deadline = 0.0
        self._pending: tuple[asyncio.AbstractEventLoop, asyncio.Future] | None = None

    # ------------------------------------------------------------------ API
    def status(self) -> dict:
        with self._lock:
            restante = 0
            if self._estado in _VISIBLE:
                restante = max(0, math.ceil(self._deadline - time.monotonic()))
            return {
                "estado": self._estado,
                "codigo": self._codigo,
                "recibidos": self._recibidos,
                "restante_s": restante,
                "ultimo_error": self._ultimo_error,
            }

    def start(self) -> None:
        """Abre la ventana de sincronización. Sin efecto si ya hay una en marcha."""
        with self._lock:
            if self._estado not in _REPOSO:
                return
            self._gen += 1
            gen = self._gen
            self._deadline = time.monotonic() + self._discoverable_s
            self._set(estado=ESPERANDO_EMPAREJAMIENTO, codigo=None, recibidos=0, ultimo_error=None)
        threading.Thread(target=self._abrir, args=(gen,), name="sync-abrir", daemon=True).start()
        threading.Thread(target=self._vigilar, args=(gen,), name="sync-plazo", daemon=True).start()

    def confirm(self, accept: bool) -> None:
        """Respuesta del usuario al código de emparejamiento que se está mostrando."""
        with self._lock:
            if self._estado != CONFIRMAR_CODIGO:
                return
            pendiente = self._tomar_pendiente()
            if accept:
                self._set(estado=ESPERANDO_EMPAREJAMIENTO, codigo=None)
            else:
                self._gen += 1
                self._set(estado=IDLE, codigo=None)
        self._resolver(pendiente, accept)
        if not accept:
            self._parar_transporte()

    def cancel(self) -> None:
        """Cierra la ventana (o corta la sincronización en curso) y vuelve a IDLE."""
        with self._lock:
            if self._estado == IDLE:
                return
            habia_ciclo = self._estado not in _REPOSO
            self._gen += 1
            pendiente = self._tomar_pendiente()
            self._set(estado=IDLE, codigo=None, ultimo_error=None)
        if habia_ciclo:
            self._parar_transporte()
        self._resolver(pendiente, False)

    # ------------------------------------------------------------- internos
    def _set(self, **cambios) -> None:
        """Aplica los cambios y notifica. Llamar con ``_lock`` tomado."""
        for nombre, valor in cambios.items():
            setattr(self, f"_{nombre}", valor)
        try:
            self._on_change(self.status())
        except Exception as exc:  # un fallo de la GUI no debe tumbar la sincronización
            print(f"[sync] on_change falló: {exc!r}", file=sys.stderr)

    def _tomar_pendiente(self):
        pendiente, self._pending = self._pending, None
        return pendiente

    @staticmethod
    def _resolver(pendiente, valor: bool) -> None:
        """Entrega la decisión al bucle asyncio que espera el código (el de BlueZ)."""
        if pendiente is None:
            return
        loop, future = pendiente

        def poner() -> None:
            if not future.done():
                future.set_result(valor)

        try:
            loop.call_soon_threadsafe(poner)
        except RuntimeError:
            pass  # ese bucle ya terminó

    def _parar_transporte(self, blocking: bool = True) -> None:
        if not self._transport_lock.acquire(blocking=blocking):
            return  # otro hilo ya lo está parando o reabriendo
        try:
            self.transport.stop()
        except Exception as exc:
            print(f"[sync] no se pudo parar el transporte: {exc!r}", file=sys.stderr)
        finally:
            self._transport_lock.release()

    def _abrir(self, gen: int) -> None:
        error = None
        with self._transport_lock:
            with self._lock:
                if gen != self._gen:
                    return  # se canceló antes de empezar
            try:
                self.transport.begin_pairing(self._on_passkey)
                self.transport.serve(self._on_connection)
            except Exception as exc:
                error = str(exc) if isinstance(exc, BluetoothUnavailable) else f"{type(exc).__name__}: {exc}"
                try:
                    self.transport.stop()
                except Exception:
                    pass
        if error is not None:
            with self._lock:
                if gen == self._gen:
                    self._set(estado=ERROR, codigo=None, ultimo_error=error)

    def _vigilar(self, gen: int) -> None:
        """Si nadie se conecta a tiempo, el PC deja de ser visible y se vuelve a IDLE."""
        while True:
            time.sleep(0.05)
            with self._lock:
                if gen != self._gen or self._estado in _REPOSO:
                    return
                if self._estado not in _VISIBLE or time.monotonic() < self._deadline:
                    continue  # hay una sesión en curso, o todavía queda tiempo
                self._gen += 1
                pendiente = self._tomar_pendiente()
                self._set(
                    estado=IDLE,
                    codigo=None,
                    ultimo_error=f"TIEMPO_AGOTADO: nadie se conectó en {self._discoverable_s} s",
                )
            self._parar_transporte()
            self._resolver(pendiente, False)  # un código sin responder se rechaza solo
            return

    async def _on_passkey(self, code: str) -> bool:
        """Lo llama el transporte (en su bucle asyncio) cuando BlueZ pide confirmar un código."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        with self._lock:
            if self._estado not in _VISIBLE:
                return False
            anterior = self._tomar_pendiente()
            self._pending = (loop, future)
            self._set(estado=CONFIRMAR_CODIGO, codigo=str(code))
        self._resolver(anterior, False)
        try:
            return await future
        except asyncio.CancelledError:
            # El transporte retiró la petición: el teléfono canceló o BlueZ dejó de esperar.
            # Se deja de mostrar el código y se sigue esperando.
            with self._lock:
                if self._pending is not None and self._pending[1] is future:
                    self._pending = None
                    if self._estado == CONFIRMAR_CODIGO:
                        self._set(estado=ESPERANDO_EMPAREJAMIENTO, codigo=None)
            raise

    def _on_connection(self, conn: Connection) -> None:
        """Lo llama el transporte, en un hilo suyo, por cada teléfono que se conecta."""
        with self._lock:
            aceptar = self._estado in _VISIBLE
            if aceptar:
                gen = self._gen
                pendiente = self._tomar_pendiente()
                self._set(estado=CONECTADO, codigo=None, recibidos=0, ultimo_error=None)
        if not aceptar:
            conn.close()
            return
        self._resolver(pendiente, False)

        terminada = False
        fallo: Exception | None = None

        def on_event(nombre: str, datos: dict) -> None:
            nonlocal terminada
            with self._lock:
                if gen != self._gen:
                    return
                if nombre == "hello":
                    self._set(estado=RECIBIENDO)
                elif nombre == "progress":
                    self._set(recibidos=datos["recibidos"])
                elif nombre == "done":
                    terminada = True

        try:
            Session(conn, self.store, on_event).run()
        except Exception as exc:  # la sesión no debería dejar escapar nada
            fallo = exc

        with self._lock:
            if gen != self._gen:
                return  # cancelada: no se revive el ciclo
            if fallo is not None:
                self._set(estado=ERROR, ultimo_error=f"SESION: {fallo!r}")
            elif not terminada:
                # Corte antes del BYE: la ventana sigue abierta para que el teléfono reintente.
                self._deadline = time.monotonic() + self._discoverable_s
                self._set(
                    estado=ESPERANDO_EMPAREJAMIENTO,
                    ultimo_error="CORTE: la sincronización se interrumpió; el teléfono puede reintentar",
                )
                return
            else:
                self._set(estado=PROCESANDO)

        # Este hilo es del transporte: si otro hilo ya lo está parando, no se espera.
        self._parar_transporte(blocking=False)
        if fallo is not None:
            return

        # D9: el teléfono ya recibió su BYE; el batch corre aquí, fuera de la sesión.
        try:
            _procesados, errores = self.store.run_batch("SYNC") or (0, 0)
        except Exception as exc:
            resultado = {"estado": ERROR, "ultimo_error": f"BATCH: {exc}"}
        else:
            resultado = {"estado": LISTO}
            try:   # el aviso es lo de menos: si falla, la sincronización ya está hecha
                self.store.notificar_sincronizacion(errores)
            except Exception:
                logging.getLogger("btsync.controller").exception("no se pudo crear la notificación de la sincronización")
        with self._lock:
            if gen == self._gen:
                self._set(**resultado)
