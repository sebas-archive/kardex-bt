"""Notificaciones globales tipo «isla dinámica» (NotificationService).

Uso desde cualquier módulo, sin pasar la ventana::

    from app import isla
    isla.exito("Datos guardados")
    isla.error("No se pudo guardar", detalle=mensaje)
    id_ = isla.cargando("Sincronizando inventario…")
    isla.actualizar(id_, isla.NotificationType.SUCCESS, "Sincronización completada")

Los textos pasan por ``i18n.t`` (se pasan en español; ``**formato`` rellena ``{campos}``). Si todavía no hay
ventana instalada (pruebas de una vista sola) las llamadas no hacen nada. Son seguras desde hilos secundarios.
"""

from __future__ import annotations

import itertools

from PyQt6.QtWidgets import QWidget

from . import textos as _textos
from .gestor import NotificationManager
from .modelo import Notification, NotificationQueue, NotificationType

__all__ = ["NotificationManager", "NotificationType", "Notification", "NotificationQueue", "instalar", "gestor",
           "notificar", "exito", "error", "advertencia", "info", "cargando", "actualizar", "cerrar"]

_textos.registrar()
_gestor: NotificationManager | None = None
_sin_ventana = itertools.count(-1, -1)   # ids de llamadas sin ventana, para que ``cargando`` devuelva algo usable


def instalar(ventana: QWidget) -> NotificationManager:
    """Crea el gestor sobre la ventana principal y lo deja como el global."""
    global _gestor
    gestor_nuevo = NotificationManager(ventana)
    _gestor = gestor_nuevo

    def _soltar(*_a, _g=gestor_nuevo) -> None:
        global _gestor
        if _gestor is _g:
            _gestor = None

    gestor_nuevo.destroyed.connect(_soltar)
    return gestor_nuevo


def gestor() -> NotificationManager | None:
    return _gestor


def _con_gestor(fn, por_omision=None):
    g = _gestor
    if g is None:
        return por_omision
    try:
        return fn(g)
    except RuntimeError:       # la ventana ya se destruyó
        return por_omision


def notificar(tipo: NotificationType, texto: str, detalle: str = "", **opciones) -> int:
    return _con_gestor(lambda g: g.notificar(tipo, texto, detalle, **opciones), next(_sin_ventana))


def exito(texto: str, detalle: str = "", **opciones) -> int:
    return notificar(NotificationType.SUCCESS, texto, detalle, **opciones)


def error(texto: str, detalle: str = "", **opciones) -> int:
    return notificar(NotificationType.ERROR, texto, detalle, **opciones)


def advertencia(texto: str, detalle: str = "", **opciones) -> int:
    return notificar(NotificationType.WARNING, texto, detalle, **opciones)


def info(texto: str, detalle: str = "", **opciones) -> int:
    return notificar(NotificationType.INFO, texto, detalle, **opciones)


def cargando(texto: str, detalle: str = "", **opciones) -> int:
    return notificar(NotificationType.LOADING, texto, detalle, **opciones)


def actualizar(id_: int, tipo: NotificationType, texto: str, detalle: str = "", **opciones) -> None:
    _con_gestor(lambda g: g.actualizar(id_, tipo, texto, detalle, **opciones))


def cerrar(id_: int) -> None:
    _con_gestor(lambda g: g.cerrar(id_))
