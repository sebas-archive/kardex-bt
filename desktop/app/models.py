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


# ---------------------------------------------------------------- formatos es-CO
def fmt_pct(valor: float) -> str:
    """80.0 → «80,0 %»."""
    return f"{valor:.1f}".replace(".", ",") + " %"


def fmt_cop(valor: float) -> str:
    """Pesos sin decimales y con punto de miles: 11800 → «$ 11.800», -5000 → «-$ 5.000»."""
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


@dataclass(frozen=True)
class PerfilDatos:
    """Cómo es la información de un conteo: volumen, quién la capturó y su calidad."""

    total_lecturas: int
    vigentes: int
    por_operador: list[tuple[str, int]]
    por_dispositivo: list[tuple[str, int]]
    filas_error: int            # filas del tránsito (todos los conteos) que el batch dejó en ERROR
    filas_total: int            # filas del tránsito ya resueltas: PROCESADO + ERROR
    fecha_min: datetime | None
    fecha_max: datetime | None
