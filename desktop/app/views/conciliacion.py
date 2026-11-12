"""Vista «Conciliación»: una fila por SKU con lo contado contra el sistema."""

from __future__ import annotations

import csv
from pathlib import Path

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import db
from ..models import FilaConciliacion, Lectura, fmt_cop, fmt_num, fmt_pct
from .base import QueryRunner, StateBanner

COLUMNAS = ("SKU", "Producto", "Categoría", "Sistema", "Contada", "Diferencia", "Dif. %", "Valor",
            "Clasificación")
CLASIFICACIONES = ("OK", "FALTANTE", "SOBRANTE", "SIN_CONTAR")
COLORES = {"OK": "#e3f4e8", "FALTANTE": "#fbe3e1", "SOBRANTE": "#fdf1d6", "SIN_CONTAR": "#e9ebee"}
NUMERICAS = {3, 4, 5, 6, 7}


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
            return QBrush(QColor(COLORES.get(f.clasificacion, "#ffffff")))
        if rol == Qt.ItemDataRole.ForegroundRole:
            return QBrush(QColor("#1f2933"))
        if rol == Qt.ItemDataRole.TextAlignmentRole and c in NUMERICAS:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None


class DetalleLecturas(QDialog):
    """Todas las lecturas de un SKU, por ubicación, marcando cuál es la vigente (D13)."""

    ENCABEZADOS = ("Ubicación", "Cantidad", "Operador", "Fecha (UTC)", "Vigente", "Nota")

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
            celdas = (l.cod_ubicacion, fmt_num(l.cantidad), l.operador or "—",
                      l.fecha_captura.strftime("%Y-%m-%d %H:%M:%S"),
                      "Sí" if l.vigente else "No (reemplazada)", l.nota or "")
            for c, texto in enumerate(celdas):
                item = QTableWidgetItem(texto)
                if not l.vigente:
                    item.setForeground(QBrush(QColor("#98a2b3")))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()


def _cargar(id_conteo: str, clasificacion, categoria, texto):
    """Corre en un hilo de trabajo: (filas filtradas, categorías del conteo)."""
    filas = db.fetch_conciliacion(id_conteo, clasificacion, categoria, texto)
    categorias = [c for c, _ in db.fetch_dif_por_categoria(id_conteo)]
    return filas, categorias


class ConciliacionView(QWidget):
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
        self.txt_buscar.setPlaceholderText("Buscar SKU o producto")
        self.txt_buscar.setClearButtonEnabled(True)
        self.btn_exportar = QPushButton("Exportar CSV")
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)

        self.modelo = ConciliacionModel()
        self.table = QTableView()
        self.table.setModel(self.modelo)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        barra = QHBoxLayout()
        barra.addWidget(QLabel("Clasificación:"))
        barra.addWidget(self.combo_clasificacion)
        barra.addWidget(QLabel("Categoría:"))
        barra.addWidget(self.combo_categoria)
        barra.addWidget(self.txt_buscar, 1)
        barra.addWidget(self.btn_exportar)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(16, 16, 16, 16)
        raiz.addLayout(barra)
        raiz.addWidget(self.banner)
        raiz.addWidget(self.table, 1)

        self._retardo = QTimer(self)
        self._retardo.setSingleShot(True)
        self._retardo.setInterval(250)
        self._retardo.timeout.connect(self.refresh)
        self.combo_clasificacion.currentIndexChanged.connect(lambda _: self.refresh())
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
    def _mostrar(self, datos) -> None:
        filas, categorias = datos
        self._cargado = True
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
