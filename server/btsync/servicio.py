"""El servicio Bluetooth independiente (Fase 5): ``python -m btsync.servicio``.

Corre aparte del escritorio (en Docker, el servicio ``bluetooth``, que arranca con el sistema) y mantiene abierta la
recepción: cada vez que ``SyncController`` vuelve al reposo, abre otra ventana de visibilidad. Una vez por segundo
(``tick``) escribe su estado y un latido en ``SERVICIO_BT`` (una fila, ``id = 1``) y lee lo que deja el escritorio:

* ``pausado = 'S'``: deja de aceptar teléfonos. Una sincronización en curso termina antes (se ve ``PAUSANDO``).
* ``respuesta``: la decisión sobre el código de emparejamiento que se está mostrando (``S``/``N``).

Un fallo de Oracle en un tick se registra y el siguiente lo reintenta: el servicio nunca se cae por eso.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable

from .controller import CONECTADO, ERROR, IDLE, LISTO, PROCESANDO, RECIBIENDO, SyncController
from .store import ddl_tolerante

TABLA = "servicio_bt"   # las pruebas usan «servicio_bt_tst»
PAUSANDO, PAUSADO, DETENIDO = "PAUSANDO", "PAUSADO", "DETENIDO"
EN_CURSO = (CONECTADO, RECIBIENDO, PROCESANDO)   # pausar espera a que terminen
REINTENTO_S = 10                                 # tras un ERROR (p. ej. sin adaptador), espera antes de reabrir
log = logging.getLogger("btsync.servicio")


def migrar(conn) -> None:
    """Crea la tabla si falta. Idempotente y tolerante a dos procesos a la vez."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :t", t=TABLA.upper())
    if not cur.fetchone()[0]:
        ddl_tolerante(cur, f"""CREATE TABLE {TABLA} (
            id            NUMBER             PRIMARY KEY,
            estado        VARCHAR2(30 CHAR)  NOT NULL,
            codigo        VARCHAR2(10 CHAR),
            recibidos     NUMBER             DEFAULT 0 NOT NULL,
            ultimo_error  VARCHAR2(400 CHAR),
            desde         TIMESTAMP          DEFAULT SYSTIMESTAMP NOT NULL,
            latido        TIMESTAMP          DEFAULT SYSTIMESTAMP NOT NULL,
            pausado       CHAR(1)            DEFAULT 'N' NOT NULL,
            respuesta     CHAR(1),
            listos        NUMBER             DEFAULT 0 NOT NULL)""")
    conn.commit()


class Servicio:
    def __init__(self, controller: SyncController, conectar: Callable, reloj: Callable[[], float] = time.monotonic,
                 periodicas: list[Callable[[], None]] | None = None) -> None:
        self.controller = controller
        self._conectar = conectar
        self._reloj = reloj
        self._conn = None
        self._pausado = False
        self._listos = 0
        self._listo_contado = False
        self._error_desde: float | None = None
        self.periodicas = periodicas or []   # cada tick, en un hilo aparte (p. ej. el respaldo automático)
        self._hilo: threading.Thread | None = None

    # ------------------------------------------------------------------ API
    def arrancar(self) -> None:
        """Deja la fila lista (conserva la pausa y el contador de sincronizaciones) con ``desde`` = ahora."""
        from . import esquema

        conn = self._conexion()
        esquema.migrar(conn)
        cur = conn.cursor()
        cur.execute(f"MERGE INTO {TABLA} s USING (SELECT 1 id FROM dual) x ON (s.id = x.id) "
                    f"WHEN MATCHED THEN UPDATE SET desde = SYSTIMESTAMP, latido = SYSTIMESTAMP, estado = :e, "
                    f"codigo = NULL, respuesta = NULL "
                    f"WHEN NOT MATCHED THEN INSERT (id, estado) VALUES (1, :e)", e=IDLE)
        cur.execute(f"SELECT pausado, listos FROM {TABLA} WHERE id = 1")
        pausado, listos = cur.fetchone()
        self._pausado, self._listos = pausado == "S", int(listos)
        conn.commit()

    def tick(self) -> None:
        respuesta = self._leer()
        antes = self.controller.status()["estado"]
        if antes == LISTO and not self._listo_contado:
            self._listos += 1
            self._listo_contado = True
        elif antes != LISTO:
            self._listo_contado = False
        if antes == ERROR and self._error_desde is None:
            self._error_desde = self._reloj()
        elif antes != ERROR:
            self._error_desde = None

        if respuesta is not None and antes == "CONFIRMAR_CODIGO":
            self.controller.confirm(respuesta == "S")
        if self._pausado:
            if antes not in EN_CURSO:
                self.controller.cancel()
        elif antes in (IDLE, LISTO) or (antes == ERROR and self._reloj() - self._error_desde >= REINTENTO_S):
            self.controller.start()

        self._escribir(respuesta)
        if self.periodicas and not self.ocupado():
            # En otro hilo: un respaldo automático largo no debe congelar el latido (el escritorio vería DETENIDO).
            self._hilo = threading.Thread(target=self._periodicas, name="servicio-periodicas", daemon=True)
            self._hilo.start()

    def ocupado(self) -> bool:
        """Si las tareas periódicas de un tick anterior siguen corriendo (no se lanza otra tanda)."""
        return self._hilo is not None and self._hilo.is_alive()

    def _periodicas(self) -> None:
        for tarea in list(self.periodicas):
            try:
                tarea()
            except Exception:   # una tarea periódica que falla no detiene la recepción
                log.exception("falló una tarea periódica del servicio")

    def correr(self) -> None:
        self.arrancar()
        while True:
            self.tick()
            time.sleep(1)

    # ------------------------------------------------------------- internos
    def _conexion(self):
        if self._conn is None:
            self._conn = self._conectar()
        return self._conn

    def _soltar(self) -> None:
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass
        self._conn = None

    def _leer(self) -> str | None:
        """Lee la pausa (se recuerda la última si Oracle no responde) y la respuesta al código."""
        try:
            cur = self._conexion().cursor()
            cur.execute(f"SELECT pausado, respuesta FROM {TABLA} WHERE id = 1")
            fila = cur.fetchone()
            if fila is None:
                return None
            self._pausado = fila[0] == "S"
            return fila[1]
        except Exception:
            log.exception("no se pudo leer el estado del servicio en Oracle")
            self._soltar()
            return None

    def _escribir(self, respuesta: str | None) -> None:
        st = self.controller.status()
        estado = st["estado"]
        if self._pausado:
            estado = PAUSANDO if estado in EN_CURSO else PAUSADO
        try:
            conn = self._conexion()
            cur = conn.cursor()
            cur.execute(f"UPDATE {TABLA} SET estado = :e, codigo = :c, recibidos = :r, ultimo_error = :u, "
                        f"latido = SYSTIMESTAMP, listos = :l WHERE id = 1",
                        e=estado, c=st["codigo"], r=st["recibidos"], u=(st["ultimo_error"] or "")[:400] or None,
                        l=self._listos)
            if respuesta is not None:
                cur.execute(f"UPDATE {TABLA} SET respuesta = NULL WHERE id = 1 AND respuesta = :r", r=respuesta)
            conn.commit()
        except Exception:
            log.exception("no se pudo escribir el estado del servicio en Oracle")
            self._soltar()


def crear_transporte():
    """``BT_TRANSPORT=bluez`` (por defecto: Bluetooth real) o ``tcp`` (pruebas y demo de respaldo)."""
    modo = os.environ.get("BT_TRANSPORT", "bluez").lower()
    if modo == "tcp":
        from .transports.tcp import TcpTransport

        return TcpTransport(os.environ.get("BT_TCP_HOST", "127.0.0.1"), int(os.environ.get("BT_TCP_PORT", "9000")))
    if modo == "bluez":
        from .transports.bluez import BluezTransport

        return BluezTransport(require_pairing=os.environ.get("BT_CON_CLAVE") == "1")
    raise SystemExit(f"BT_TRANSPORT inválido: {modo!r} (usa «bluez» o «tcp»)")


def main() -> int:
    from .store import Store, connect_oracle

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    dsn, user, password = os.environ["DB_DSN"], os.environ["DB_USER"], os.environ["DB_PASSWORD"]
    store = Store(dsn, user, password)
    controller = SyncController(crear_transporte(), store, lambda _status: None)
    from . import respaldo

    def conectar():
        return connect_oracle(dsn, user, password)

    servicio = Servicio(controller, conectar, periodicas=[respaldo.Automatico(conectar)])
    log.info("servicio Bluetooth en marcha")
    servicio.correr()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
