"""Modelo puro de las notificaciones «isla»: tipos, datos y cola. No importa Qt: se prueba sin interfaz."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NotificationType(Enum):
    """Categoría de la notificación: define color, icono, duración y prioridad por omisión."""

    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    LOADING = "loading"

    @property
    def duracion_ms(self) -> int | None:
        """``None``: no se cierra sola (la carga espera a que la operación termine)."""
        return {"success": 3000, "error": 5000, "warning": 4000, "info": 3000, "loading": None}[self.value]

    @property
    def prioridad(self) -> int:
        return {"error": 3, "warning": 2}.get(self.value, 1)


@dataclass
class Notification:
    id: int
    tipo: NotificationType
    texto: str                       # ya traducido
    detalle: str = ""                # segunda línea, más pequeña (opcional)
    duracion_ms: int | None = None   # ``None`` = la del tipo
    prioridad: int | None = None     # ``None`` = la del tipo

    def __post_init__(self) -> None:
        if self.duracion_ms is None:
            self.duracion_ms = self.tipo.duracion_ms
        if self.prioridad is None:
            self.prioridad = self.tipo.prioridad
        if self.tipo is NotificationType.LOADING:
            self.duracion_ms = None

    def misma_que(self, otra: "Notification") -> bool:
        return (self.tipo, self.texto, self.detalle) == (otra.tipo, otra.texto, otra.detalle)


class NotificationQueue:
    """Cola por prioridad (mayor primero) y, a igual prioridad, por orden de llegada."""

    def __init__(self, maximo: int = 30) -> None:
        self._items: list[Notification] = []
        self.maximo = maximo

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(list(self._items))

    def ultima(self) -> Notification | None:
        return self._items[-1] if self._items else None

    def buscar(self, id_: int) -> Notification | None:
        return next((n for n in self._items if n.id == id_), None)

    def agregar(self, noti: Notification) -> None:
        self._items.append(noti)
        if len(self._items) > self.maximo:
            # Se pierde la más antigua de menor prioridad; nunca una carga (alguien espera su resultado).
            candidatas = [n for n in self._items if n.tipo is not NotificationType.LOADING]
            if candidatas:
                self._items.remove(min(candidatas, key=lambda n: (n.prioridad, -self._items.index(n))))

    def al_frente(self, noti: Notification) -> None:
        self._items.insert(0, noti)

    def sacar(self) -> Notification | None:
        if not self._items:
            return None
        mejor = max(self._items, key=lambda n: n.prioridad)   # max devuelve la primera: respeta el orden de llegada
        self._items.remove(mejor)
        return mejor

    def quitar(self, id_: int) -> Notification | None:
        noti = self.buscar(id_)
        if noti is not None:
            self._items.remove(noti)
        return noti

    def hay_mas_urgente_que(self, prioridad: int) -> bool:
        return any(n.prioridad > prioridad for n in self._items)
