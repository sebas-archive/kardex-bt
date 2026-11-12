"""Filas que devuelve la capa de datos. Sin lógica: la conciliación la calcula Oracle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Conteo:
    id_conteo: str
    nombre: str
    estado: str  # ABIERTO | CERRADO


@dataclass(frozen=True)
class ResumenConteo:
    """Una fila de V_RESUMEN_CONTEO."""

    id_conteo: str
    skus_totales: int
    contados: int
    avance_pct: float
    ok: int
    faltantes: int
    sobrantes: int
    exactitud_pct: float
    valor_faltante: float
    valor_sobrante: float

    @property
    def sin_contar(self) -> int:
        return self.skus_totales - self.contados


@dataclass(frozen=True)
class FilaConciliacion:
    sku: str
    nombre: str
    categoria: str
    cant_sistema: float | None
    cant_contada: float | None
    diferencia: float | None
    diferencia_pct: float | None
    valor_diferencia: float | None
    clasificacion: str  # OK | FALTANTE | SOBRANTE | SIN_CONTAR


@dataclass(frozen=True)
class Lectura:
    """Una lectura procesada de un SKU en una ubicación (``vigente`` = la que cuenta, D13)."""

    cod_ubicacion: str
    cantidad: float
    operador: str | None
    fecha_captura: datetime
    vigente: bool
    nota: str | None


@dataclass(frozen=True)
class EstadoBatch:
    """Una fila de V_ESTADO_BATCH."""

    pendientes: int
    procesando: int
    procesados: int
    errores: int
    ultimo_run: datetime | None
    ultimo_origen: str | None


@dataclass(frozen=True)
class ErrorFila:
    """Una fila del staging que el batch dejó en ERROR."""

    id_transito: int
    uuid_dispositivo: str
    seq: int
    mensaje_error: str | None
    datos_raw: str
    fecha_recepcion: datetime | None
