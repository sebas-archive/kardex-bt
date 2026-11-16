"""Pantalla «Notificaciones»: lo que pasó en el sistema y le importa a esta persona (no son solicitudes).

La más reciente primero, ● en las sin leer, filtro «Todas | Sin leer», «Marcar todas como leídas» y, en las que
llevan a otra pantalla, «Ver» (que además la marca leída). Emite ``cambiaron`` al marcar, para que la campana se
actualice.
"""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import auth, notificaciones
from ..i18n import registrar, t
from .base import QueryRunner, StateBanner

registrar({
    "Avisos del sistema: sincronizaciones, cuentas, respaldos y el servicio. Las solicitudes se aprueban en "
    "«Solicitudes».":
        "System notices: syncs, accounts, backups and the service. Requests are approved in “Requests”.",
    "Todas": "All",
    "Sin leer": "Unread",
    "Marcar todas como leídas": "Mark all as read",
    "Fecha": "Date",
    "Aviso": "Notice",
    "Ver": "View",
    "Hoy {hora}": "Today {hora}",
    "Ayer {hora}": "Yesterday {hora}",
    "No hay notificaciones sin leer.": "There are no unread notifications.",
    "Aún no hay notificaciones.": "There are no notifications yet.",
    "Marcar todas las notificaciones como leídas": "Mark all notifications as read",
})

ENCABEZADOS = ("", "Fecha", "Aviso", "")
TODAS, SIN_LEER = "Todas", "Sin leer"


def _fecha(f) -> str:
    hoy = date.today()
    if f.date() == hoy:
        return t("Hoy {hora}", hora=f"{f:%H:%M}")
    if (hoy - f.date()).days == 1:
        return t("Ayer {hora}", hora=f"{f:%H:%M}")
    return f"{f:%d/%m %H:%M}"


class NotificacionesView(QWidget):
    ir_a = pyqtSignal(str)       # «Ver»: el título de la pantalla relacionada
    cambiaron = pyqtSignal()     # se marcó algo como leído

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._todas: list[notificaciones.Notificacion] = []
        self._visibles: list[notificaciones.Notificacion] = []

        ayuda = QLabel(t("Avisos del sistema: sincronizaciones, cuentas, respaldos y el servicio. Las solicitudes "
                         "se aprueban en «Solicitudes»."))
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.combo_filtro = QComboBox()
        self.combo_filtro.addItems([t(TODAS), t(SIN_LEER)])
        self.btn_todas = QPushButton(t("Marcar todas como leídas"))
        barra = QHBoxLayout()
        barra.addStretch(1)
        barra.addWidget(self.combo_filtro)
        barra.addWidget(self.btn_todas)

        self.tabla = QTableWidget(0, len(ENCABEZADOS))
        self.tabla.setHorizontalHeaderLabels([t(c) for c in ENCABEZADOS])
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(36)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for c in (0, 1):
            cabecera.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        cabecera.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)   # ResizeToContents no cuenta el botón de la celda
        self.tabla.setColumnWidth(3, 92)

        tarjeta = QFrame()
        tarjeta.setObjectName("card")
        cuerpo = QVBoxLayout(tarjeta)
        cuerpo.setContentsMargins(16, 14, 16, 14)
        cuerpo.addLayout(barra)
        cuerpo.addWidget(self.banner)
        cuerpo.addWidget(self.tabla, 1)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(12)
        raiz.addWidget(ayuda)
        raiz.addWidget(tarjeta, 1)

        self.combo_filtro.currentIndexChanged.connect(lambda _i: self._filtrar())
        self.btn_todas.clicked.connect(self._marcar_todas)

    # ------------------------------------------------- contrato de las vistas
    def acciones_paleta(self):
        from .paleta import Atajo

        return [Atajo("notif:todas", t("Marcar todas las notificaciones como leídas"), t("Notificaciones"), "",
                      self.btn_todas.click, habilitado=self.btn_todas.isEnabled)]

    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:
            self._mostrar([])
        self.refresh()

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("notificaciones"):
            return
        self._runner.run(notificaciones.listar, self._mostrar, self.banner.show_error, self._sesion, key="lista")

    # ------------------------------------------------------------- pruebas
    def filas(self) -> list[tuple[str, str, str]]:
        return [tuple(self.tabla.item(f, c).text() if self.tabla.item(f, c) else "" for c in range(3))
                for f in range(self.tabla.rowCount())]

    def boton_ver(self, fila: int) -> QPushButton | None:
        return self.tabla.cellWidget(fila, 3)

    # ------------------------------------------------------------- internos
    def _mostrar(self, lista) -> None:
        self.banner.clear()
        self._todas = list(lista)
        self._filtrar()

    def _filtrar(self) -> None:
        solo = self.combo_filtro.currentText() == t(SIN_LEER)
        self._visibles = [n for n in self._todas if not (solo and n.leida)]
        self.tabla.setRowCount(len(self._visibles))
        for f, n in enumerate(self._visibles):
            punto = QTableWidgetItem("" if n.leida else "●")
            if not n.leida:
                punto.setForeground(self.palette().highlight())
            self.tabla.setItem(f, 0, punto)
            self.tabla.setItem(f, 1, QTableWidgetItem(_fecha(n.fecha)))
            texto = QTableWidgetItem(n.texto)
            if not n.leida:
                fuente = texto.font()
                fuente.setBold(True)
                texto.setFont(fuente)
            self.tabla.setItem(f, 2, texto)
            if n.seccion:
                boton = QPushButton(t("Ver"))
                boton.setObjectName("verAviso")
                boton.setCursor(Qt.CursorShape.PointingHandCursor)
                boton.setFixedHeight(26)
                boton.clicked.connect(lambda _c=False, x=n: self._ver(x))
                self.tabla.setCellWidget(f, 3, boton)
            else:
                self.tabla.removeCellWidget(f, 3)
                self.tabla.setItem(f, 3, QTableWidgetItem(""))
        if not self._visibles:
            self.banner.show_empty(t("No hay notificaciones sin leer.") if solo else t("Aún no hay notificaciones."))
        self.btn_todas.setEnabled(any(not n.leida for n in self._todas))

    def _ver(self, n: notificaciones.Notificacion) -> None:
        if self._sesion is not None and not n.leida:
            self._runner.run(notificaciones.marcar_leida, self._marcado, lambda _m: None, self._sesion, n.id)
        self.ir_a.emit(n.seccion)

    def _marcar_todas(self) -> None:
        if self._sesion is not None:
            self._runner.run(notificaciones.marcar_todas, self._marcado, self.banner.show_error, self._sesion)

    def _marcado(self, _r) -> None:
        self.cambiaron.emit()
        self.refresh()
