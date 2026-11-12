"""Vista «Perfil»: cómo es la información (campos, reglas de clasificación, tolerancias y calidad)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGroupBox,
    QHeaderView,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import db
from ..models import PerfilDatos, fmt_num, fmt_pct
from .base import QueryRunner, StateBanner
from .conciliacion import COLORES

CAMPOS = (
    ("SKU", "texto", "Código de barras del producto (el escáner del celular lee el SKU)."),
    ("Sistema", "número", "Cantidad teórica en la foto de stock tomada al abrir el conteo."),
    ("Contada", "número", "Suma de las lecturas vigentes del SKU en todas las ubicaciones."),
    ("Diferencia", "número", "Contada − Sistema. Vacía mientras el SKU está sin contar."),
    ("Dif. %", "porcentaje", "Diferencia ÷ Sistema × 100. Vacía si Sistema es 0."),
    ("Valor", "pesos (COP)", "Diferencia × costo unitario. Negativo = faltante, positivo = sobrante."),
    ("Clasificación", "texto", "OK, FALTANTE, SOBRANTE o SIN_CONTAR (reglas abajo)."),
    ("Ubicación", "texto", "Estante donde se contó. Recontar la misma ubicación reemplaza la lectura anterior."),
    ("Operador", "texto (≤ 60)", "Quién contó; lo escribe el operario en el celular."),
    ("Fecha de captura", "fecha UTC", "Hora del celular corregida con la hora del servidor al sincronizar."),
)
CLASIFICACIONES = {
    "OK": "La diferencia absoluta no supera Sistema × tolerancia % de la categoría (el límite cuenta como OK).",
    "FALTANTE": "Contada es menor que Sistema y la diferencia supera la tolerancia.",
    "SOBRANTE": "Contada es mayor que Sistema fuera de tolerancia, o Sistema es 0 y se contó algo.",
    "SIN_CONTAR": "Nadie lo contó y el conteo sigue abierto; cuando se cierra el conteo pasa a FALTANTE con contada 0.",
}
INDICADORES = ("Lecturas procesadas", "Por operador", "Por dispositivo", "Filas con error", "Fechas capturadas")


def _cargar(id_conteo: str) -> tuple[PerfilDatos, list[tuple[str, float, float, int]]]:
    """Corre en un hilo de trabajo."""
    return db.fetch_perfil(id_conteo), db.fetch_tolerancias()


def _tolerancia(minimo: float, maximo: float) -> str:
    if minimo == maximo:
        return f"{fmt_num(minimo)} %"
    return f"{fmt_num(minimo)}–{fmt_num(maximo)} %"


def _tabla(encabezados: tuple[str, ...], filas: int = 0) -> QTableWidget:
    tabla = QTableWidget(filas, len(encabezados))
    tabla.setHorizontalHeaderLabels(list(encabezados))
    tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tabla.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    tabla.verticalHeader().hide()
    cabecera = tabla.horizontalHeader()
    for i in range(len(encabezados) - 1):
        cabecera.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
    cabecera.setSectionResizeMode(len(encabezados) - 1, QHeaderView.ResizeMode.Stretch)  # la última se estira
    tabla.setWordWrap(True)
    tabla.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return tabla


def _ajustar(tabla: QTableWidget) -> None:
    """Alto exacto de las filas: las tablas no tienen barra vertical, la vista entera se desplaza."""
    tabla.resizeRowsToContents()
    alto = tabla.horizontalHeader().height() + sum(tabla.rowHeight(r) for r in range(tabla.rowCount())) + 4
    tabla.setFixedHeight(alto)


class PerfilView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._id: str | None = None
        self._cargado = False
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)

        self.tbl_campos = _tabla(("Campo", "Tipo", "Qué significa"), len(CAMPOS))
        for r, fila in enumerate(CAMPOS):
            for c, texto in enumerate(fila):
                self.tbl_campos.setItem(r, c, QTableWidgetItem(texto))
        self.tbl_clasificaciones = _tabla(("Clasificación", "Regla"), len(CLASIFICACIONES))
        for r, (nombre, regla) in enumerate(CLASIFICACIONES.items()):
            item = QTableWidgetItem(nombre)
            item.setBackground(QBrush(QColor(COLORES[nombre])))
            item.setForeground(QBrush(QColor("#1f2933")))
            self.tbl_clasificaciones.setItem(r, 0, item)
            self.tbl_clasificaciones.setItem(r, 1, QTableWidgetItem(regla))
        self.tbl_tolerancias = _tabla(("Categoría", "Tolerancia", "SKU"))
        self.tbl_estadisticas = _tabla(("Indicador", "Valor"), len(INDICADORES))
        for r, nombre in enumerate(INDICADORES):
            self.tbl_estadisticas.setItem(r, 0, QTableWidgetItem(nombre))
            self.tbl_estadisticas.setItem(r, 1, QTableWidgetItem("—"))

        self._secciones: list[QGroupBox] = []
        contenido = QWidget()
        lay = QVBoxLayout(contenido)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.addWidget(self.banner)
        for titulo, tabla in (
            ("Campos de la conciliación", self.tbl_campos),
            ("Clasificaciones", self.tbl_clasificaciones),
            ("Tolerancia por categoría", self.tbl_tolerancias),
            ("Calidad y volumen de la información", self.tbl_estadisticas),
        ):
            caja = QGroupBox(titulo)
            QVBoxLayout(caja).addWidget(tabla)
            lay.addWidget(caja)
            self._secciones.append(caja)
        lay.addStretch(1)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setWidget(contenido)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(desplazable)
        self._reajustar()

    # ------------------------------------------------------------------ API
    def titulos_de_seccion(self) -> list[str]:
        return [caja.title() for caja in self._secciones]

    def campos(self) -> list[tuple[str, str, str]]:
        return list(CAMPOS)

    def clasificaciones(self) -> dict[str, str]:
        return self._pares(self.tbl_clasificaciones)

    def tolerancias(self) -> dict[str, str]:
        return self._pares(self.tbl_tolerancias)

    def estadisticas(self) -> dict[str, str]:
        return self._pares(self.tbl_estadisticas)

    def set_conteo(self, id_conteo: str | None) -> None:
        self._id, self._cargado = id_conteo, False
        self._valores_estadisticas({n: "—" for n in INDICADORES})
        self.refresh()

    def refresh(self) -> None:
        if self._id is None:
            self.banner.show_empty("Sin datos")
            return
        if not self._cargado:
            self.banner.show_loading()
        self._runner.run(_cargar, self._mostrar, self.banner.show_error, self._id, key="perfil")

    # ------------------------------------------------------------- internos
    def _reajustar(self) -> None:
        for tabla in (self.tbl_campos, self.tbl_clasificaciones, self.tbl_tolerancias, self.tbl_estadisticas):
            _ajustar(tabla)

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        QTimer.singleShot(0, self._reajustar)  # el alto de las filas depende del estilo y del ancho ya definitivos

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        QTimer.singleShot(0, self._reajustar)  # con otro ancho cambian las líneas de los textos largos

    @staticmethod
    def _pares(tabla: QTableWidget) -> dict[str, str]:
        return {tabla.item(r, 0).text(): tabla.item(r, 1).text() for r in range(tabla.rowCount())}

    def _valores_estadisticas(self, valores: dict[str, str]) -> None:
        for r, nombre in enumerate(INDICADORES):
            self.tbl_estadisticas.item(r, 1).setText(valores[nombre])
        _ajustar(self.tbl_estadisticas)

    def _mostrar(self, datos) -> None:
        perfil, tolerancias = datos
        self._cargado = True
        self.tbl_tolerancias.setRowCount(len(tolerancias))
        for r, (categoria, minimo, maximo, skus) in enumerate(tolerancias):
            for c, texto in enumerate((categoria, _tolerancia(minimo, maximo), str(skus))):
                self.tbl_tolerancias.setItem(r, c, QTableWidgetItem(texto))
        _ajustar(self.tbl_tolerancias)

        if perfil.total_lecturas == 0:
            self._valores_estadisticas({n: "—" for n in INDICADORES})
            self.banner.show_empty("Sin datos")
            return
        self.banner.clear()
        error = "—"
        if perfil.filas_total:
            error = (f"{perfil.filas_error} de {perfil.filas_total} "
                     f"({fmt_pct(100 * perfil.filas_error / perfil.filas_total)})")
        self._valores_estadisticas({
            "Lecturas procesadas": f"{perfil.total_lecturas} ({perfil.vigentes} vigentes, "
                                   f"{perfil.total_lecturas - perfil.vigentes} reemplazadas)",
            "Por operador": _unir(perfil.por_operador),
            "Por dispositivo": _unir(perfil.por_dispositivo),
            "Filas con error": error,
            "Fechas capturadas": f"{perfil.fecha_min:%Y-%m-%d %H:%M:%S} → {perfil.fecha_max:%Y-%m-%d %H:%M:%S} (UTC)",
        })


def _unir(pares: list[tuple[str, int]]) -> str:
    return " · ".join(f"{nombre or '(sin operador)'} {n}" for nombre, n in pares) or "—"
