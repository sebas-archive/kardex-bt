"""Dashboard personalizable: catálogo de lo que se puede mostrar, distribución de cada usuario y su persistencia.

Solo se ofrece lo que tiene datos reales en el sistema (conteo continuo, conciliación por categoría, lecturas por
hora, actividad por operador, dañados, procesamiento del batch y auditoría). No hay entradas/salidas, stock bajo ni
valor de inventario porque el esquema no los registra.

Persistencia: ``QSettings`` por usuario (clave ``dashboard/<usuario>``). No toca el esquema de Oracle; la
distribución es una preferencia de visualización de cada persona en este equipo.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from PyQt6.QtCore import QSettings

from .i18n import registrar

TAMANOS = ("S", "M", "L")
NOMBRE_TAMANO = {"S": "Pequeño", "M": "Mediano", "L": "Grande"}

CATEGORIAS = ("Inventario", "Conciliación", "Sincronización", "Actividad", "Estadísticas")

KPI, PANEL, GRAFICO = "kpi", "panel", "grafico"

TIPOS_GRAFICO = ("barras", "barras_h", "lineas", "area", "circular", "anillo", "apiladas", "comparativo", "evolucion")
NOMBRE_TIPO = {
    "barras": "Barras verticales", "barras_h": "Barras horizontales", "lineas": "Líneas", "area": "Áreas",
    "circular": "Circular", "anillo": "Anillo", "apiladas": "Barras apiladas", "comparativo": "Comparativo",
    "evolucion": "Evolución temporal",
}

PERIODOS = ("todo", "hoy", "7d", "30d", "90d", "mes", "anio", "personalizado")
NOMBRE_PERIODO = {
    "todo": "Todo el conteo", "hoy": "Hoy", "7d": "Últimos 7 días", "30d": "Últimos 30 días",
    "90d": "Últimos 90 días", "mes": "Este mes", "anio": "Este año", "personalizado": "Personalizado",
}
AGRUPACIONES = ("auto", "minuto", "hora", "dia")
NOMBRE_AGRUPACION = {"auto": "Automática", "minuto": "Por minuto", "hora": "Por hora", "dia": "Por día"}
ORDENES = ("original", "valor_desc", "valor_asc", "nombre")
NOMBRE_ORDEN = {"original": "Original", "valor_desc": "Mayor a menor", "valor_asc": "Menor a mayor", "nombre": "Por nombre"}

registrar({
    "Pequeño": "Small", "Mediano": "Medium", "Grande": "Large",
    "Inventario": "Inventory", "Conciliación": "Reconciliation", "Sincronización": "Synchronization",
    "Actividad": "Activity", "Estadísticas": "Statistics",
    "Barras verticales": "Vertical bars", "Barras horizontales": "Horizontal bars", "Líneas": "Lines", "Áreas": "Areas",
    "Circular": "Pie", "Anillo": "Donut", "Barras apiladas": "Stacked bars", "Comparativo": "Comparison",
    "Evolución temporal": "Time evolution",
    "Todo el conteo": "Whole count", "Hoy": "Today", "Últimos 7 días": "Last 7 days", "Últimos 30 días": "Last 30 days",
    "Últimos 90 días": "Last 90 days", "Este mes": "This month", "Este año": "This year", "Personalizado": "Custom",
    "Automática": "Automatic", "Por minuto": "Per minute", "Por hora": "Per hour", "Por día": "Per day",
    "Original": "Original", "Mayor a menor": "High to low", "Menor a mayor": "Low to high", "Por nombre": "By name",
})


@dataclass(frozen=True)
class Def:
    """Una cosa que se puede poner en el dashboard."""

    clave: str
    tipo: str                      # kpi | panel | grafico
    nombre: str
    descripcion: str
    categoria: str
    modulo: str = "dashboard"      # permiso necesario para verlo (la matriz de roles)
    tams: tuple[str, ...] = TAMANOS
    tam: str = "S"                 # tamaño al agregarlo
    tipos: tuple[str, ...] = ()    # gráficos: los tipos de visualización compatibles
    tipo_defecto: str = ""
    temporal: bool = False         # tiene eje de tiempo (período y agrupación)
    drill: bool = False            # el clic en una categoría filtra el inventario
    unico: bool = True             # solo una vez (los gráficos se pueden repetir)


CATALOGO: tuple[Def, ...] = (
    # ------------------------------------------------------------- inventario
    Def("avance", KPI, "Avance del conteo", "Porcentaje de productos que ya tienen una lectura.", "Inventario"),
    Def("contados", KPI, "Productos contados", "Productos con al menos una lectura registrada.", "Inventario"),
    Def("sin_contar", KPI, "Productos sin contar", "Productos que todavía no tienen lectura.", "Inventario"),
    # ------------------------------------------------------------- conciliación
    Def("coincidentes", KPI, "Coinciden con el sistema", "Contados cuya cantidad es igual a la del sistema (y su exactitud).",
        "Conciliación"),
    Def("faltantes", KPI, "Faltantes", "Productos contados con menos unidades que el sistema.", "Conciliación"),
    Def("sobrantes", KPI, "Sobrantes", "Productos contados con más unidades que el sistema.", "Conciliación"),
    # ------------------------------------------------------------- sincronización
    Def("con_error", KPI, "Lecturas con error", "Lecturas recibidas que no pudieron procesarse.", "Sincronización"),
    Def("batch", PANEL, "Última sincronización", "Cuándo corrió el último procesamiento y cómo terminó.",
        "Sincronización", tams=("M", "L"), tam="L"),
    # ------------------------------------------------------------- actividad
    Def("actividad_reciente", PANEL, "Actividad reciente", "Lo último que se hizo en el sistema (auditoría).",
        "Actividad", modulo="auditoria", tams=("M", "L"), tam="M"),
    # ------------------------------------------------------------- estadísticas (gráficos)
    Def("dif_categoria", GRAFICO, "Diferencia por categoría", "Unidades de más o de menos frente al sistema.",
        "Estadísticas", tam="L", tipos=("barras", "barras_h"), tipo_defecto="barras", drill=True, unico=False),
    Def("avance_categoria", GRAFICO, "Avance por categoría", "Porcentaje contado de cada categoría.",
        "Estadísticas", tam="M", tipos=("barras", "barras_h", "lineas", "area"), tipo_defecto="barras_h", drill=True,
        unico=False),
    Def("lecturas_categoria", GRAFICO, "Lecturas por categoría", "Cuántas lecturas recibió cada categoría.",
        "Estadísticas", tam="M", tipos=("barras", "barras_h", "circular", "anillo"), tipo_defecto="anillo",
        drill=True, unico=False),
    Def("danados", GRAFICO, "Dañados por categoría", "Unidades dañadas registradas en las lecturas vigentes.",
        "Estadísticas", tam="M", tipos=("barras", "barras_h", "circular", "anillo"), tipo_defecto="barras_h",
        drill=True, unico=False),
    Def("contados_pendientes", GRAFICO, "Contados frente a pendientes", "Productos contados y productos por contar.",
        "Estadísticas", tam="S", tipos=("anillo", "circular", "barras"), tipo_defecto="anillo", unico=False),
    Def("lecturas_tiempo", GRAFICO, "Lecturas en el tiempo", "Cuántas lecturas llegan en cada momento.",
        "Estadísticas", tam="L", tipos=("evolucion", "lineas", "area", "barras"), tipo_defecto="evolucion",
        temporal=True, unico=False),
    Def("operador", GRAFICO, "Lecturas por operador", "Cuántas lecturas aportó cada operador.", "Actividad",
        tam="M", tipos=("barras", "barras_h", "circular", "anillo"), tipo_defecto="barras_h", temporal=True,
        unico=False),
    Def("operador_tiempo", GRAFICO, "Operadores en el tiempo", "Lecturas de cada operador a lo largo del tiempo.",
        "Actividad", tam="L", tipos=("apiladas", "comparativo", "lineas", "area"), tipo_defecto="apiladas",
        temporal=True, unico=False),
    Def("batch_corridas", GRAFICO, "Procesamiento por corrida", "Lecturas procesadas y con error en cada corrida.",
        "Sincronización", tam="M", tipos=("apiladas", "comparativo", "lineas", "area"), tipo_defecto="comparativo",
        temporal=True, unico=False),
)

POR_CLAVE = {d.clave: d for d in CATALOGO}

registrar({
    "Avance del conteo": "Count progress", "Productos contados": "Counted products",
    "Productos sin contar": "Uncounted products", "Coinciden con el sistema": "Match the system",
    "Faltantes": "Short", "Sobrantes": "Over", 
    "Lecturas con error": "Readings with error", 
    "Última sincronización": "Last synchronization", "Actividad reciente": "Recent activity",
    "Diferencia por categoría": "Difference by category", "Avance por categoría": "Progress by category",
    "Lecturas por categoría": "Readings by category", "Dañados por categoría": "Damaged by category",
    "Contados frente a pendientes": "Counted vs pending", "Lecturas en el tiempo": "Readings over time",
    "Lecturas por operador": "Readings by operator", "Operadores en el tiempo": "Operators over time",
    "Procesamiento por corrida": "Processing per run",
    "Porcentaje de productos que ya tienen una lectura.": "Share of products that already have a reading.",
    "Productos del catálogo incluidos en el conteo.": "Catalog products included in the count.",
    "Productos con al menos una lectura registrada.": "Products with at least one reading.",
    "Productos que todavía no tienen lectura.": "Products that do not have a reading yet.",
    "Contados cuya cantidad es igual a la del sistema (y su exactitud).": "Counted products whose quantity equals the system's (and their accuracy).",
    "Productos contados con menos unidades que el sistema.": "Counted products with fewer units than the system.",
    "Productos contados con más unidades que el sistema.": "Counted products with more units than the system.",
    "Porcentaje de contados que coinciden con el sistema.": "Share of counted products that match the system.",
    "Lecturas recibidas que no pudieron procesarse.": "Received readings that could not be processed.",
    "Datos recibidos que esperan al batch.": "Received data waiting for the batch.",
    "Cuándo corrió el último procesamiento y cómo terminó.": "When the last run happened and how it ended.",
    "Lo último que se hizo en el sistema (auditoría).": "The latest actions in the system (audit log).",
    "Unidades de más o de menos frente al sistema.": "Units over or under the system.",
    "Porcentaje contado de cada categoría.": "Share counted in each category.",
    "Cuántas lecturas recibió cada categoría.": "How many readings each category received.",
    "Unidades dañadas registradas en las lecturas vigentes.": "Damaged units recorded in current readings.",
    "Productos contados y productos por contar.": "Counted products and products still to count.",
    "Cuántas lecturas llegan en cada momento.": "How many readings arrive at each moment.",
    "Cuántas lecturas aportó cada operador.": "How many readings each operator contributed.",
    "Lecturas de cada operador a lo largo del tiempo.": "Each operator's readings over time.",
    "Lecturas procesadas y con error en cada corrida.": "Processed readings and errors in each run.",
})


@dataclass
class Item:
    """Un widget puesto en el dashboard de una persona."""

    clave: str
    tam: str = "S"
    opciones: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    @property
    def definicion(self) -> Def:
        return POR_CLAVE[self.clave]


def opciones_por_defecto(d: Def) -> dict:
    if d.tipo != GRAFICO:
        return {}
    return {"titulo": "", "tipo": d.tipo_defecto, "periodo": "todo", "desde": "", "hasta": "", "agrupar": "auto",
            "orden": "original", "top": 0, "leyenda": True, "etiquetas": True}


def nuevo(clave: str, tam: str | None = None) -> Item:
    d = POR_CLAVE[clave]
    return Item(clave, tam or d.tam, opciones_por_defecto(d))


def predeterminado() -> list[Item]:
    """La distribución inicial: los cuatro indicadores del conteo, la diferencia por categoría y el batch."""
    return [nuevo("avance"), nuevo("contados"), nuevo("faltantes"), nuevo("sobrantes"),
            nuevo("dif_categoria"), nuevo("batch")]


def permitido(d: Def, sesion) -> bool:
    """Un widget solo se ofrece (y se muestra) si el rol de la persona puede consultar su módulo."""
    return sesion is None or sesion.puede(d.modulo)


def normalizar(items: list[Item], sesion=None) -> list[Item]:
    """Descarta lo que ya no existe en el catálogo o que el rol no puede ver; repara tamaños y opciones."""
    salida: list[Item] = []
    for it in items:
        d = POR_CLAVE.get(it.clave)
        if d is None or not permitido(d, sesion):
            continue
        if d.unico and any(x.clave == it.clave for x in salida):
            continue
        tam = it.tam if it.tam in d.tams else d.tam
        base = opciones_por_defecto(d)
        opciones = {**base, **{k: v for k, v in (it.opciones or {}).items() if k in base}}
        if d.tipo == GRAFICO and opciones["tipo"] not in d.tipos:
            opciones["tipo"] = d.tipo_defecto
        salida.append(Item(d.clave, tam, opciones, it.id))
    return salida


# ----------------------------------------------------------------------------- persistencia por usuario
def _ajustes() -> QSettings:
    return QSettings("GestionInventario", "Dashboard")


def _clave(usuario: str) -> str:
    return f"dashboard/{usuario}"


def a_json(items: list[Item]) -> str:
    return json.dumps({"v": 1, "items": [{"id": i.id, "clave": i.clave, "tam": i.tam, "opciones": i.opciones}
                                         for i in items]}, ensure_ascii=False)


def de_json(texto: str) -> list[Item] | None:
    try:
        datos = json.loads(texto)
        return [Item(str(x["clave"]), str(x.get("tam", "S")), dict(x.get("opciones") or {}),
                     str(x.get("id") or uuid.uuid4().hex[:10])) for x in datos["items"]]
    except (ValueError, KeyError, TypeError):
        return None


def cargar(usuario: str, sesion=None) -> list[Item]:
    """La distribución guardada de esa persona; si no hay (o está dañada), la predeterminada."""
    texto = _ajustes().value(_clave(usuario), "")
    items = de_json(str(texto)) if texto else None
    if items is None:
        return normalizar(predeterminado(), sesion)
    return normalizar(items, sesion)


def guardar(usuario: str, items: list[Item]) -> None:
    ajustes = _ajustes()
    ajustes.setValue(_clave(usuario), a_json(items))
    ajustes.sync()


def restaurar(usuario: str) -> list[Item]:
    ajustes = _ajustes()
    ajustes.remove(_clave(usuario))
    ajustes.sync()
    return predeterminado()
