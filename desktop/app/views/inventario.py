"""Pantalla «Inventario»: una fila por producto con lo contado contra el sistema, búsqueda y filtros rápidos."""

from __future__ import annotations

import csv
from pathlib import Path

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QPainter
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyledItemDelegate,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import db
from ..models import FilaConciliacion, Lectura, fmt_cop, fmt_num, fmt_pct
from .base import QueryRunner, StateBanner
from .widgets import COLOR_CLASIFICACION, NOMBRE_CLASIFICACION, Chip

COLUMNAS = ("SKU", "Producto", "Categoría", "Sistema", "Contada", "Diferencia", "Dif. %", "Valor",
            "Clasificación")
CLASIFICACIONES = ("OK", "FALTANTE", "SOBRANTE", "SIN_CONTAR")
COLORES = {"OK": "#111111", "FALTANTE": "#2A1412", "SOBRANTE": "#2A200E", "SIN_CONTAR": "#161616"}
NUMERICAS = {3, 4, 5, 6, 7}
COL_PCT, COL_CLASIFICACION = 6, 8


class BarraPctDelegate(QStyledItemDelegate):
    """Columna «Dif. %»: detrás del número, una barra que sale del centro (izquierda si falta, derecha si sobra)."""

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        super().paint(painter, option, index)
        pct = index.model().fila(index.row()).diferencia_pct
        if not pct:
            return
        r = option.rect
        tope = max(10.0, index.model().max_pct())  # la barra más larga es la mayor diferencia que se está viendo
        medio, alcance = r.left() + r.width() / 2, (r.width() / 2 - 4) * min(abs(pct) / tope, 1.0)
        color = QColor(COLOR_CLASIFICACION["FALTANTE" if pct < 0 else "SOBRANTE"])
        color.setAlpha(110)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(medio - alcance if pct < 0 else medio, r.bottom() - 7, alcance, 5), 2.5, 2.5)
        painter.restore()


class InsigniaDelegate(QStyledItemDelegate):
    """Columna «Clasificación»: una píldora del color de la clasificación en vez del texto en mayúsculas."""

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        clase = index.model().fila(index.row()).clasificacion
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(option.rect, QColor(COLORES.get(clase, "#111111")))
        texto = NOMBRE_CLASIFICACION.get(clase, clase)
        ancho = painter.fontMetrics().horizontalAdvance(texto) + 20
        caja = QRectF(option.rect.left() + 8, option.rect.center().y() - 10, ancho, 20)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLOR_CLASIFICACION.get(clase, "#98A2B3")))
        painter.drawRoundedRect(caja, 10, 10)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(caja, Qt.AlignmentFlag.AlignCenter, texto)
        painter.restore()


class ConciliacionModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._filas: list[FilaConciliacion] = []

    def set_filas(self, filas: list[FilaConciliacion]) -> None:
        self.beginResetModel()
        self._filas = list(filas)
        self.endResetModel()

    def fila(self, i: int) -> FilaConciliacion:
        return self._filas[i]

    def max_pct(self) -> float:
        """La mayor |diferencia %| de las filas mostradas (escala de las barras de esa columna)."""
        return max((abs(f.diferencia_pct) for f in self._filas if f.diferencia_pct is not None), default=0.0)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._filas)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMNAS)

    def headerData(self, seccion, orientacion, rol=Qt.ItemDataRole.DisplayRole):
        if orientacion == Qt.Orientation.Horizontal and rol == Qt.ItemDataRole.DisplayRole:
            return COLUMNAS[seccion]
        return None

    def data(self, index: QModelIndex, rol=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        f, c = self._filas[index.row()], index.column()
        if rol == Qt.ItemDataRole.DisplayRole:
            return (
                f.sku, f.nombre, f.categoria, fmt_num(f.cant_sistema), fmt_num(f.cant_contada),
                fmt_num(f.diferencia),
                "—" if f.diferencia_pct is None else fmt_pct(f.diferencia_pct),
                "—" if f.valor_diferencia is None else fmt_cop(f.valor_diferencia),
                f.clasificacion,
            )[c]
        if rol == Qt.ItemDataRole.BackgroundRole:
            return QBrush(QColor(COLORES.get(f.clasificacion, "#111111")))
        if rol == Qt.ItemDataRole.ForegroundRole:
            return QBrush(QColor("#EDEDED"))
        if rol == Qt.ItemDataRole.TextAlignmentRole and c in NUMERICAS:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None


class DetalleLecturas(QDialog):
    """Todas las lecturas de un SKU, marcando cuál es la vigente (la más reciente, D13)."""

    ENCABEZADOS = ("Cantidad", "Operador", "Fecha (UTC)", "Vigente", "Nota")

    def __init__(self, id_conteo: str, sku: str, nombre: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Lecturas de {sku} — {nombre}")
        self.resize(720, 320)
        self._runner = QueryRunner(self)
        self.banner = StateBanner()
        self.banner.retry.connect(lambda: self._cargar(id_conteo, sku))
        self.table = QTableWidget(0, len(self.ENCABEZADOS))
        self.table.setHorizontalHeaderLabels(self.ENCABEZADOS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        lay = QVBoxLayout(self)
        lay.addWidget(self.banner)
        lay.addWidget(self.table)
        self._cargar(id_conteo, sku)

    def _cargar(self, id_conteo: str, sku: str) -> None:
        self.banner.show_loading()
        self._runner.run(db.fetch_lecturas, self._mostrar, self.banner.show_error, id_conteo, sku, key="lecturas")

    def _mostrar(self, lecturas: list[Lectura]) -> None:
        if not lecturas:
            self.banner.show_empty("Sin lecturas para este SKU")
        else:
            self.banner.clear()
        self.table.setRowCount(len(lecturas))
        for r, l in enumerate(lecturas):
            celdas = (fmt_num(l.cantidad), l.operador or "—",
                      l.fecha_captura.strftime("%Y-%m-%d %H:%M:%S"),
                      "Sí" if l.vigente else "No (reemplazada)", l.nota or "")
            for c, texto in enumerate(celdas):
                item = QTableWidgetItem(texto)
                if not l.vigente:
                    item.setForeground(QBrush(QColor("#98a2b3")))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()


def _cargar(id_conteo: str, clasificacion, categoria, texto):
    """Corre en un hilo de trabajo: (filas filtradas, categorías del conteo, SKU por clasificación)."""
    filas = db.fetch_conciliacion(id_conteo, clasificacion, categoria, texto)
    categorias = [c for c, _ in db.fetch_dif_por_categoria(id_conteo)]
    return filas, categorias, db.fetch_distribucion(id_conteo)


class InventarioView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._id: str | None = None
        self._cargado = False
        self.detalle: DetalleLecturas | None = None

        self.combo_clasificacion = QComboBox()
        self.combo_clasificacion.addItem("Todas")
        self.combo_clasificacion.addItems(CLASIFICACIONES)
        self.combo_categoria = QComboBox()
        self.combo_categoria.addItem("Todas")
        self.txt_buscar = QLineEdit()
        self.txt_buscar.setPlaceholderText("Buscar por SKU o nombre del producto")
        self.txt_buscar.setClearButtonEnabled(True)
        self.btn_exportar = QPushButton("Exportar CSV")
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)

        # Filtros rápidos por clasificación, con cuántos SKU hay en cada una (van a la par del combo).
        self.chips: dict[str, Chip] = {}
        self._grupo_chips = QButtonGroup(self)
        self._grupo_chips.setExclusive(True)
        fila_chips = QHBoxLayout()
        fila_chips.setSpacing(8)
        for clave in ("Todas",) + CLASIFICACIONES:
            chip = Chip(NOMBRE_CLASIFICACION.get(clave, clave))
            chip.clicked.connect(lambda _=False, c=clave: self.combo_clasificacion.setCurrentText(c))
            self._grupo_chips.addButton(chip)
            self.chips[clave] = chip
            fila_chips.addWidget(chip)
        self.chips["Todas"].setChecked(True)
        fila_chips.addStretch(1)
        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setObjectName("resumen")

        self.modelo = ConciliacionModel()
        self.table = QTableView()
        self.table.setModel(self.modelo)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setItemDelegateForColumn(COL_PCT, BarraPctDelegate(self.table))
        self.table.setItemDelegateForColumn(COL_CLASIFICACION, InsigniaDelegate(self.table))
        self.table.verticalHeader().setDefaultSectionSize(34)

        barra = QHBoxLayout()
        self.combo_clasificacion.hide()  # los chips de arriba hacen lo mismo; el combo queda como estado interno
        barra.addWidget(QLabel("Categoría"))
        barra.addWidget(self.combo_categoria)
        barra.addWidget(self.txt_buscar, 1)
        barra.addWidget(self.btn_exportar)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(10)
        raiz.addLayout(fila_chips)
        raiz.addLayout(barra)
        raiz.addWidget(self.banner)
        raiz.addWidget(self.table, 1)
        raiz.addWidget(self.lbl_resumen)  # el total de lo que se está viendo

        self._retardo = QTimer(self)
        self._retardo.setSingleShot(True)
        self._retardo.setInterval(250)
        self._retardo.timeout.connect(self.refresh)
        self.combo_clasificacion.currentIndexChanged.connect(self._clasificacion_cambiada)
        self.combo_categoria.currentIndexChanged.connect(lambda _: self.refresh())
        self.txt_buscar.textChanged.connect(lambda _: self._retardo.start())
        self.btn_exportar.clicked.connect(self._elegir_archivo)
        self.table.doubleClicked.connect(self._doble_clic)

    # ------------------------------------------------------------------ API
    def set_conteo(self, id_conteo: str | None) -> None:
        self._id, self._cargado = id_conteo, False
        self.modelo.set_filas([])
        self.refresh()

    def refresh(self) -> None:
        if self._id is None:
            self.modelo.set_filas([])
            self.banner.show_empty("Sin datos")
            return
        if not self._cargado:
            self.banner.show_loading()
        clasificacion = self.combo_clasificacion.currentText()
        categoria = self.combo_categoria.currentText()
        self._runner.run(
            _cargar, self._mostrar, self.banner.show_error, self._id,
            None if clasificacion == "Todas" else clasificacion,
            None if categoria == "Todas" else categoria,
            self.txt_buscar.text(),
            key="conciliacion",
        )

    def abrir_detalle(self, sku: str) -> None:
        fila = next((f for f in self.modelo._filas if f.sku == sku), None)
        if self._id is None or fila is None:
            return
        self.detalle = DetalleLecturas(self._id, sku, fila.nombre, self)
        self.detalle.show()

    def exportar_csv(self, ruta: str | Path) -> None:
        """Escribe las filas que se están viendo (con los filtros). Separador «;» y BOM: abre bien en Excel."""
        def num(valor) -> str:
            return "" if valor is None else fmt_num(valor)

        with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
            escritor = csv.writer(fh, delimiter=";")
            escritor.writerow(COLUMNAS)
            for f in self.modelo._filas:
                escritor.writerow([f.sku, f.nombre, f.categoria, num(f.cant_sistema), num(f.cant_contada),
                                   num(f.diferencia), num(f.diferencia_pct), num(f.valor_diferencia),
                                   f.clasificacion])

    # ------------------------------------------------------------- internos
    def _clasificacion_cambiada(self, _indice: int) -> None:
        self.chips[self.combo_clasificacion.currentText()].setChecked(True)
        self.refresh()

    def _mostrar(self, datos) -> None:
        filas, categorias, distribucion = datos
        self._cargado = True
        self.chips["Todas"].setText(f"Todas  {sum(distribucion.values())}")
        for clase in CLASIFICACIONES:
            self.chips[clase].setText(f"{NOMBRE_CLASIFICACION[clase]}  {distribucion.get(clase, 0)}")
        faltante = sum(f.valor_diferencia or 0 for f in filas if f.clasificacion == "FALTANTE")
        sobrante = sum(f.valor_diferencia or 0 for f in filas if f.clasificacion == "SOBRANTE")
        neto = sum(f.valor_diferencia or 0 for f in filas)
        self.lbl_resumen.setText(
            f"{len(filas)} SKU · faltante {fmt_cop(faltante)} · sobrante {fmt_cop(sobrante)} · neto {fmt_cop(neto)}")
        actual = self.combo_categoria.currentText()
        self.combo_categoria.blockSignals(True)
        self.combo_categoria.clear()
        self.combo_categoria.addItem("Todas")
        self.combo_categoria.addItems(categorias)
        indice = self.combo_categoria.findText(actual)
        self.combo_categoria.setCurrentIndex(max(indice, 0))
        self.combo_categoria.blockSignals(False)
        self.modelo.set_filas(filas)
        self.table.resizeColumnsToContents()
        if filas:
            self.banner.clear()
        else:
            self.banner.show_empty("Sin datos")

    def _doble_clic(self, indice: QModelIndex) -> None:
        if indice.isValid():
            self.abrir_detalle(self.modelo.fila(indice.row()).sku)

    def _elegir_archivo(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar conciliación", "conciliacion.csv", "CSV (*.csv)")
        if ruta:
            self.exportar_csv(ruta)
