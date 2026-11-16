"""NotificationManager: decide qué cápsula se muestra y cuándo. Vive en el hilo de la interfaz.

Se puede llamar desde cualquier hilo: cada pedido viaja por una señal (en cola si viene de otro hilo), así que el
estado y los widgets solo se tocan desde la interfaz.
"""

from __future__ import annotations

import itertools

from PyQt6.QtCore import QEvent, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget

from .. import i18n
from .modelo import Notification, NotificationQueue, NotificationType
from .widget import NotificationWidget

_ids = itertools.count(1)


class NotificationManager(QObject):
    _pide_mostrar = pyqtSignal(object)
    _pide_actualizar = pyqtSignal(int, object, str, str, object)
    _pide_cerrar = pyqtSignal(int)

    def __init__(self, ventana: QWidget) -> None:
        super().__init__(ventana)
        self._ventana = ventana
        self.cola = NotificationQueue()
        self.widget = NotificationWidget(ventana)
        self.widget.oculta.connect(self._al_ocultar)
        self._alias: dict[int, int] = {}          # id de un duplicado descartado -> id de la que sí se muestra
        self._reencolar: Notification | None = None
        self._pide_mostrar.connect(self._mostrar)
        self._pide_actualizar.connect(self._actualizar)
        self._pide_cerrar.connect(self._cerrar)
        ventana.installEventFilter(self)

    # ------------------------------------------------------------------ API (cualquier hilo)
    def notificar(self, tipo: NotificationType, texto: str, detalle: str = "", *, duracion_ms: int | None = None,
                  prioridad: int | None = None, **formato) -> int:
        noti = Notification(next(_ids), tipo, i18n.t(texto, **formato), i18n.t(detalle, **formato) if detalle else "",
                            duracion_ms, prioridad)
        self._pide_mostrar.emit(noti)
        return noti.id

    def actualizar(self, id_: int, tipo: NotificationType, texto: str, detalle: str = "", *,
                   duracion_ms: int | None = None, **formato) -> None:
        """Transforma la notificación ``id_`` (p. ej. una carga) en otra, sin cerrarla ni abrir una nueva."""
        self._pide_actualizar.emit(id_, tipo, i18n.t(texto, **formato),
                                   i18n.t(detalle, **formato) if detalle else "", duracion_ms)

    def cerrar(self, id_: int) -> None:
        self._pide_cerrar.emit(id_)

    # ------------------------------------------------------------------ consulta (hilo de la interfaz)
    def textos(self) -> list[str]:
        """Texto de la cápsula visible y de las que esperan (para pruebas y diagnóstico)."""
        visibles = [self.widget.texto()] if self.widget.activa else []
        return visibles + [n.texto for n in self.cola]

    def pendientes(self) -> int:
        return len(self.cola)

    # ------------------------------------------------------------------ lógica
    def _actual(self) -> Notification | None:
        return self.widget._noti if self.widget.activa else None

    def _resolver(self, id_: int) -> int:
        return self._alias.get(id_, id_)

    def _mostrar(self, noti: Notification) -> None:
        actual = self._actual()
        ultima = self.cola.ultima() or self._reencolar or actual
        if ultima is not None and ultima.misma_que(noti):
            self._alias[noti.id] = ultima.id          # duplicado consecutivo: no se repite
            return
        if actual is None and self._reencolar is None and not self.widget.saliendo:
            self.widget.presentar(noti)
            return
        self.cola.agregar(noti)
        # Una carga larga no debe tapar un error o una advertencia que acaba de llegar.
        if (actual is not None and actual.tipo is NotificationType.LOADING and not self.widget.saliendo
                and noti.prioridad > actual.prioridad):
            self._reencolar = actual
            self.widget.ocultar()

    def _actualizar(self, id_: int, tipo: NotificationType, texto: str, detalle: str, duracion_ms) -> None:
        id_ = self._resolver(id_)
        nueva = Notification(id_, tipo, texto, detalle, duracion_ms)
        actual = self._actual()
        if actual is not None and actual.id == id_ and not self.widget.saliendo:
            self.widget.transformar(nueva)
            return
        if self._reencolar is not None and self._reencolar.id == id_:
            self._reencolar = nueva
            return
        enlazada = self.cola.buscar(id_)
        if enlazada is not None:       # todavía no se mostró: se muestra ya como resultado final
            enlazada.tipo, enlazada.texto, enlazada.detalle = nueva.tipo, nueva.texto, nueva.detalle
            enlazada.duracion_ms, enlazada.prioridad = nueva.duracion_ms, nueva.prioridad
            return
        if tipo is not NotificationType.LOADING:   # la carga se cerró a mano o se perdió: el resultado se muestra
            self._mostrar(nueva)

    def _cerrar(self, id_: int) -> None:
        id_ = self._resolver(id_)
        actual = self._actual()
        if actual is not None and actual.id == id_:
            self.widget.ocultar()
        elif self._reencolar is not None and self._reencolar.id == id_:
            self._reencolar = None
        else:
            self.cola.quitar(id_)

    def _al_ocultar(self, _id: int) -> None:
        if self._reencolar is not None:
            self.cola.al_frente(self._reencolar)
            self._reencolar = None
        QTimer.singleShot(60, self._siguiente)

    def _siguiente(self) -> None:
        if self.widget.activa:
            return
        siguiente = self.cola.sacar()
        if siguiente is not None:
            self.widget.presentar(siguiente)
        else:
            self._alias.clear()

    def limpiar(self) -> None:
        """Descarta todo sin animar (cierre de la ventana)."""
        self.cola = NotificationQueue()
        self._reencolar = None
        self._alias.clear()
        self.widget.cerrar_ya()

    # ------------------------------------------------------------------ ventana
    def eventFilter(self, obj, evento) -> bool:
        if obj is self._ventana:
            tipo = evento.type()
            if tipo == QEvent.Type.Resize:
                self.widget.recentrar()
            elif tipo == QEvent.Type.ChildAdded and self.widget.activa:
                QTimer.singleShot(0, self._subir)
        return False

    def _subir(self) -> None:
        try:
            if self.widget.activa:
                self.widget.raise_()
        except RuntimeError:
            pass
