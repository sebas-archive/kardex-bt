"""Filas que devuelve la capa de datos. Sin lógica de negocio: la conciliación la calcula Oracle.

El conteo es continuo y único (``ACTUAL``): no hay cierres ni varias fotos de stock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ResumenConteo:
    """Una fila de ``V_RESUMEN_CONTEO`` para el conteo continuo."""

    id_conteo: str
    skus_totales: int
    contados: int
    avance_pct: float
    ok: int
    faltantes: int
    sobrantes: int
    exactitud_pct: float

    @property
    def sin_contar(self) -> int:
        return self.skus_totales - self.contados


@dataclass(frozen=True)
class FilaInventario:
    """Una fila de la pantalla Inventario: producto, lo del sistema y lo último contado."""

    sku: str
    nombre: str
    categoria: str
    cant_contada: float | None
    cant_sistema: float | None


@dataclass(frozen=True)
class Lectura:
    """Una lectura procesada de un SKU (``vigente`` = la que cuenta: la más reciente)."""

    cantidad: float
    operador: str | None
    fecha_captura: datetime
    vigente: bool
    nota: str | None
    ruta_foto: str | None = None


@dataclass(frozen=True)
class EstadoBatch:
    """Una fila de ``V_ESTADO_BATCH``."""

    pendientes: int
    procesando: int
    procesados: int
    errores: int
    ultimo_run: datetime | None
    ultimo_origen: str | None


@dataclass(frozen=True)
class ErrorFila:
    """Una lectura que el batch dejó en ERROR (``V_ERRORES_CAPTURA``)."""

    id_transito: int
    uuid_dispositivo: str
    seq: int
    sku: str
    cantidad: str
    mensaje_error: str | None
    fecha_recepcion: datetime | None

    @property
    def motivo(self) -> str:
        return self.mensaje_error or ""


# ---------------------------------------------------------------- formatos es-CO
def fmt_pct(valor: float) -> str:
    """80.0 → «80,0 %»."""
    return f"{valor:.1f}".replace(".", ",") + " %"


def fmt_cop(valor: float) -> str:
    """Pesos sin decimales y con punto de miles: 11800 → «$ 11.800»."""
    entero = int(round(abs(valor)))
    texto = f"{entero:,}".replace(",", ".")
    return f"-$ {texto}" if valor < 0 and entero else f"$ {texto}"


def fmt_num(valor: float | None) -> str:
    """Cantidades: 45.0 → «45», 12.5 → «12,5»; sin dato → «—»."""
    if valor is None:
        return "—"
    if float(valor).is_integer():
        return str(int(valor))
    return f"{valor:.3f}".rstrip("0").rstrip(".").replace(".", ",")
