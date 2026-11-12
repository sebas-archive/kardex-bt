"""Vista «Conteo»: indicadores del conteo elegido y el botón para cerrarlo."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from .. import db
from ..models import ResumenConteo, fmt_cop, fmt_pct
from .base import QueryRunner, StateBanner

TARJETAS = (
    ("avance", "Avance"),
    ("exactitud", "Exactitud"),
    ("valor_faltante", "Valor faltante"),
    ("valor_sobrante", "Valor sobrante"),
    ("sin_contar", "SKUs sin contar"),
)
ANCHO_TARJETA = 175  # px mínimos por tarjeta: con menos ancho se acomodan en más filas


def _cargar(id_conteo: str):
    """Corre en un hilo de trabajo: (resumen, estado del conteo)."""
    resumen = db.fetch_resumen(id_conteo)
    estado = next((c.estado for c in db.fetch_conteos() if c.id_conteo == id_conteo), None)
    return resumen, estado


class ConteoView(QWidget):
    conteo_cerrado = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._id: str | None = None
        self._cargado = False

        self.titulo = QLabel("Conteo")
        self.titulo.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.subtitulo = QLabel("")
        self.subtitulo.setObjectName("subtitulo")
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)

        self.cards: dict[str, QFrame] = {}
        self._valores: dict[str, QLabel] = {}
        self._rejilla = QGridLayout()
        self._rejilla.setSpacing(12)
        for clave, titulo in TARJETAS:
            card = QFrame()
            card.setObjectName("card")
            lay = QVBoxLayout(card)
            lay.setContentsMargins(14, 12, 14, 12)
            etiqueta = QLabel(titulo)
            etiqueta.setObjectName("cardTitulo")
            valor = QLabel("—")
            valor.setObjectName("cardValor")
            lay.addWidget(etiqueta)
            lay.addWidget(valor)
            self.cards[clave], self._valores[clave] = card, valor

        self.btn_cerrar = QPushButton("Cerrar conteo")
        self.btn_cerrar.setObjectName("peligro")
        self.btn_cerrar.clicked.connect(self._pedir_cierre)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(16, 16, 16, 16)
        raiz.setSpacing(12)
        raiz.addWidget(self.titulo)
        raiz.addWidget(self.subtitulo)
        raiz.addWidget(self.banner)
        raiz.addLayout(self._rejilla)
        raiz.addWidget(self.btn_cerrar)
        raiz.addStretch(1)
        self._reacomodar()

    # ------------------------------------------------------------------ API
    def card_text(self, clave: str) -> str:
        return self._valores[clave].text()

    def set_conteo(self, id_conteo: str | None) -> None:
        self._id, self._cargado = id_conteo, False
        for valor in self._valores.values():
            valor.setText("—")
        self.btn_cerrar.setEnabled(False)
        self.btn_cerrar.setText("Cerrar conteo")
        self.subtitulo.setText("")
        self.refresh()

    def refresh(self) -> None:
        if self._id is None:
            self.banner.show_empty("Sin datos")
            return
        if not self._cargado:
            self.banner.show_loading()
        self._runner.run(_cargar, self._mostrar, self.banner.show_error, self._id, key="resumen")

    # ------------------------------------------------------------- internos
    def _mostrar(self, datos: tuple[ResumenConteo | None, str | None]) -> None:
        resumen, estado = datos
        if resumen is None:
            self.banner.show_empty("Sin datos")
            return
        self.banner.clear()
        self._cargado = True
        self._valores["avance"].setText(fmt_pct(resumen.avance_pct))
        self._valores["exactitud"].setText(fmt_pct(resumen.exactitud_pct))
        self._valores["valor_faltante"].setText(fmt_cop(resumen.valor_faltante))
        self._valores["valor_sobrante"].setText(fmt_cop(resumen.valor_sobrante))
        self._valores["sin_contar"].setText(str(resumen.sin_contar))
        self.titulo.setText(f"Conteo {resumen.id_conteo}")
        self.subtitulo.setText(
            f"{estado or '—'} · {resumen.skus_totales} SKU, {resumen.contados} contados"
        )
        cerrado = estado == "CERRADO"
        self.btn_cerrar.setEnabled(not cerrado)
        self.btn_cerrar.setText("Conteo cerrado" if cerrado else "Cerrar conteo")

    def _pedir_cierre(self) -> None:
        if self._id is None:
            return
        respuesta = QMessageBox.question(
            self,
            "Cerrar conteo",
            f"Cerrar el conteo {self._id} es irreversible: los SKU que nadie contó pasarán a faltante "
            "y ya no se aceptarán más lecturas.\n\n¿Cerrarlo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        self.btn_cerrar.setEnabled(False)
        self.btn_cerrar.setText("Cerrando…")
        id_conteo = self._id
        self._runner.run(db.cerrar_conteo, lambda _: self._cerrado(id_conteo), self._error_cierre, id_conteo)

    def _cerrado(self, id_conteo: str) -> None:
        self.conteo_cerrado.emit(id_conteo)
        self.refresh()

    def _error_cierre(self, mensaje: str) -> None:
        self.banner.show_error(mensaje)
        self.refresh()

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        self._reacomodar()

    def _reacomodar(self) -> None:
        """Tarjetas en tantas columnas como quepan (hasta 5) para que ninguna se recorte."""
        columnas = max(1, min(len(TARJETAS), self.width() // ANCHO_TARJETA))
        if getattr(self, "_columnas", None) == columnas:
            return
        self._columnas = columnas
        for card in self.cards.values():
            self._rejilla.removeWidget(card)
        for i, card in enumerate(self.cards.values()):
            self._rejilla.addWidget(card, i // columnas, i % columnas)
        for c in range(len(TARJETAS)):
            self._rejilla.setColumnStretch(c, 1 if c < columnas else 0)
