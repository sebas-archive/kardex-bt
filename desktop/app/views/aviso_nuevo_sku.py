"""Aviso flotante «Nuevo SKU»: una lectura llegó con un SKU que no está en el catálogo.

No es un error: el batch la dejó en ``NUEVO_SKU`` y espera la decisión del Administrador. El aviso vive
**encima** del contenido de la ventana (no ocupa lugar en ningún layout), arriba a la derecha, y muestra una
tarjeta por SKU con sus lecturas, «Crear y procesar» y «No crear».

- «Crear y procesar»: pide nombre y categoría (el SKU viene del aviso, en solo lectura y en mayúsculas) y el
  diálogo llama a ``db.nuevo_sku_alta``.
- «No crear»: descarta la lectura (``db.descartar_nuevo_sku``); no se cuenta.

Las señales las conecta ``MainWindow``; este módulo no consulta Oracle ni decide permisos.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..models import NuevoSkuFila
from ..tema import colores

MAX_TARJETAS = 3


def _normalizar(sku: str | None) -> str:
    return (sku or "").strip().upper()


def _agrupar(filas: list[NuevoSkuFila]) -> list[dict]:
    """Una entrada por SKU normalizado, en el orden en que llegan (la lectura más reciente primero)."""
    grupos: dict[str, dict] = {}
    for fila in filas:
        sku = _normalizar(fila.sku) or t("Sin SKU")
        grupo = grupos.get(sku)
        if grupo is None:
            grupo = {"sku": sku, "lecturas": 0, "ultima": None}
            grupos[sku] = grupo
        grupo["lecturas"] += 1
        ultima = fila.fecha_recepcion
        if ultima is not None and (grupo["ultima"] is None or ultima > grupo["ultima"]):
            grupo["ultima"] = ultima
    return list(grupos.values())


def _subtitulo(grupo: dict) -> str:
    """«3 lecturas · última 16/11 05:20»; sin fecha, solo el conteo."""
    n = grupo["lecturas"]
    texto = t("1 lectura") if n == 1 else t("{n} lecturas", n=n)
    if grupo["ultima"] is not None:
        texto += " · " + t("última {fecha}", fecha=f"{grupo['ultima']:%d/%m %H:%M}")
    return texto


def _estilo(c: dict[str, str]) -> str:
    """La estética del tema, local al aviso: se reaplica al mostrarlo (claro/oscuro sin tocar el QSS global)."""
    return f"""
    QFrame#avisoNuevoSku {{ background: transparent; }}
    QFrame#avisoNuevoSku QFrame#tarjetaAvisoSku {{
        background: {c['tarjeta']}; border: 1px solid {c['borde_fuerte']}; border-radius: 14px; }}
    QFrame#avisoNuevoSku QLabel {{ background: transparent; color: {c['texto']}; }}
    QFrame#avisoNuevoSku QLabel#tituloAviso {{ color: {c['aviso']}; font-size: 11px; font-weight: 700; }}
    QFrame#avisoNuevoSku QLabel#skuAviso {{ color: {c['texto_fuerte']}; font-size: 16px; font-weight: 700; }}
    QFrame#avisoNuevoSku QLabel#subAviso {{ color: {c['texto_suave']}; font-size: 11px; }}
    QFrame#avisoNuevoSku QLabel#masAviso {{ color: {c['texto_suave']}; font-size: 11px; font-weight: 600;
        padding: 0 4px; }}
    QFrame#avisoNuevoSku QPushButton#cerrarAviso {{ background: transparent; color: {c['texto_suave']};
        border: none; border-radius: 6px; padding: 0; font-size: 15px; font-weight: 700; }}
    QFrame#avisoNuevoSku QPushButton#cerrarAviso:hover {{ color: {c['texto_fuerte']}; background: {c['borde']}; }}
    QFrame#avisoNuevoSku QPushButton#ocultosAviso {{ background: {c['tarjeta']}; color: {c['texto_suave']};
        border: 1px solid {c['borde']}; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600; }}
    QFrame#avisoNuevoSku QPushButton#ocultosAviso:hover {{ color: {c['texto']}; border-color: {c['texto_tenue']}; }}
    QFrame#avisoNuevoSku QPushButton#crearAviso {{ background: {c['acento']}; color: {c['acento_texto']};
        border: none; border-radius: 8px; padding: 5px 12px; font-size: 12px; font-weight: 700; }}
    QFrame#avisoNuevoSku QPushButton#crearAviso:hover {{ background: {c['acento_suave']}; }}
    QFrame#avisoNuevoSku QPushButton#crearAviso:disabled {{ background: {c['borde']}; color: {c['texto_suave']}; }}
    QFrame#avisoNuevoSku QPushButton#noCrearAviso {{ background: transparent; color: {c['texto_suave']};
        border: 1px solid {c['borde_fuerte']}; border-radius: 8px; padding: 5px 12px; font-size: 12px; font-weight: 600; }}
    QFrame#avisoNuevoSku QPushButton#noCrearAviso:hover {{ color: {c['texto']}; border-color: {c['texto_tenue']}; }}
    """


class _TarjetaNuevoSku(QFrame):
    """Una tarjeta: título «Nuevo SKU», el SKU, cuántas lecturas son y las dos opciones."""

    crear = pyqtSignal(str)
    descartar = pyqtSignal(str)
    cerrar = pyqtSignal(str)

    def __init__(self, sku: str, subtitulo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("tarjetaAvisoSku")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.sku = sku
        self.setProperty("sku", sku)
        self.lbl_titulo = QLabel(t("Nuevo SKU"))
        self.lbl_titulo.setObjectName("tituloAviso")
        self.lbl_sku = QLabel(sku)
        self.lbl_sku.setObjectName("skuAviso")
        self.lbl_sku.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_subtitulo = QLabel(subtitulo)
        self.lbl_subtitulo.setObjectName("subAviso")
        self.btn_cerrar = QPushButton("×")
        self.btn_cerrar.setObjectName("cerrarAviso")
        self.btn_cerrar.setFixedSize(22, 22)
        self.btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cerrar.setToolTip(t("Ocultar por ahora (el SKU sigue pendiente)"))
        self.btn_cerrar.setAccessibleName(t("Ocultar aviso"))
        self.btn_cerrar.clicked.connect(lambda: self.cerrar.emit(self.sku))
        self.btn_crear = QPushButton(t("Crear y procesar"))
        self.btn_crear.setObjectName("crearAviso")
        self.btn_crear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_no_crear = QPushButton(t("No crear"))
        self.btn_no_crear.setObjectName("noCrearAviso")
        self.btn_no_crear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_crear.clicked.connect(lambda: self.crear.emit(self.sku))
        self.btn_no_crear.clicked.connect(lambda: self.descartar.emit(self.sku))

        # Compacta, en dos líneas: «Nuevo SKU · 1 lectura · última …» y [×]; debajo el SKU y las dos opciones.
        cabecera = QHBoxLayout()
        cabecera.setContentsMargins(0, 0, 0, 0)
        cabecera.setSpacing(6)
        cabecera.addWidget(self.lbl_titulo)
        cabecera.addWidget(self.lbl_subtitulo, 1)
        cabecera.addWidget(self.btn_cerrar)
        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(8)
        fila.addWidget(self.lbl_sku, 1)
        fila.addWidget(self.btn_no_crear)
        fila.addWidget(self.btn_crear)
        en_tarjeta = QVBoxLayout(self)
        en_tarjeta.setContentsMargins(12, 8, 10, 10)
        en_tarjeta.setSpacing(2)
        en_tarjeta.addLayout(cabecera)
        en_tarjeta.addLayout(fila)


class AvisoNuevoSku(QFrame):
    """Aviso flotante, abajo a la derecha del contenido: una tarjeta compacta por SKU nuevo (máximo 3 + «+N más»).

    Se muestra con ``mostrar(filas)`` y desaparece con ``ocultar()``. No se añade a ningún layout: flota sobre
    el contenido y se recoloca cuando la ventana cambia de tamaño (``reubicar``).
    """

    crear_solicitado = pyqtSignal(str)
    descartar_solicitado = pyqtSignal(str)

    ANCHO = 420
    MARGEN = 16

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("avisoNuevoSku")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._filas: list[NuevoSkuFila] = []
        self._firma: tuple | None = None
        self._tarjetas: list[_TarjetaNuevoSku] = []
        self.lbl_mas: QLabel | None = None
        self.btn_ocultos: QPushButton | None = None
        self._cerrados: dict[str, int] = {}   # SKU ocultado → nº de lecturas al ocultarlo
        self._en_aviso = QVBoxLayout(self)
        self._en_aviso.setContentsMargins(0, 0, 0, 0)
        self._en_aviso.setSpacing(8)
        self.hide()

    # ------------------------------------------------------------------ API
    def mostrar(self, filas: list[NuevoSkuFila]) -> None:
        """Pinta las filas recibidas. Sin filas, el aviso se oculta (no reserva espacio nunca)."""
        self._filas = list(filas)
        todos = _agrupar(self._filas)
        # Un SKU cerrado con la X vuelve solo si llegan lecturas nuevas de él; si ya no existe, se olvida.
        self._cerrados = {g["sku"]: self._cerrados[g["sku"]] for g in todos if g["sku"] in self._cerrados}
        grupos = [g for g in todos if g["lecturas"] > self._cerrados.get(g["sku"], 0)]
        ocultos = len(todos) - len(grupos)
        if not todos:
            self.ocultar()
            return
        firma = (tuple((g["sku"], g["lecturas"], g["ultima"]) for g in grupos), ocultos)
        if firma != self._firma:
            self._firma = firma
            self._pintar(grupos, ocultos)
        self._aplicar_estilo()
        self.reubicar()
        self.show()
        self.raise_()

    def ocultar(self) -> None:
        self._filas = []
        self._firma = None
        self._cerrados = {}
        self._limpiar_tarjetas()
        self.hide()

    def cerrar_sku(self, sku: str) -> None:
        """Oculta la tarjeta sin decidir nada: el SKU sigue pendiente y reaparece si llegan lecturas nuevas."""
        buscado = _normalizar(sku) or t("Sin SKU")
        for grupo in _agrupar(self._filas):
            if grupo["sku"] == buscado:
                self._cerrados[buscado] = grupo["lecturas"]
        self._firma = None
        self.mostrar(self._filas)

    def mostrar_ocultos(self) -> None:
        """Vuelve a mostrar todas las tarjetas cerradas con la X."""
        self._cerrados = {}
        self._firma = None
        self.mostrar(self._filas)

    def olvidar(self, sku: str) -> None:
        """Quita de una vez el SKU que se acaba de crear/descartar (sin esperar al siguiente sondeo)."""
        buscado = _normalizar(sku)
        self._filas = [f for f in self._filas if _normalizar(f.sku) != buscado]
        self._firma = None
        self.mostrar(self._filas)

    def retraducir(self) -> None:
        """Vuelve a pintar con el idioma vigente (se llama al cambiar de idioma)."""
        self._firma = None
        self.mostrar(self._filas)

    def reestilizar(self) -> None:
        """Reaplica los colores del tema (se llama al cambiar de tema)."""
        self._aplicar_estilo()
        if self.isVisible():
            self.reubicar()

    def reubicar(self) -> None:
        """Abajo a la derecha del área de contenido: no tapa la barra lateral, el encabezado ni «Actualizar»."""
        padre = self.parentWidget()
        if padre is None:
            return
        area = padre.area_contenido() if hasattr(padre, "area_contenido") else padre.rect()
        if area.width() < 240 or area.height() < 160:
            return
        ancho = min(self.ANCHO, max(260, area.width() - 2 * self.MARGEN))
        self.setFixedWidth(ancho)
        self.adjustSize()
        alto = min(self.height(), max(120, area.height() - 2 * self.MARGEN))
        self.resize(ancho, alto)
        x = area.right() - ancho - self.MARGEN + 1
        y = area.bottom() - alto - self.MARGEN + 1
        self.move(max(area.left() + self.MARGEN, x), max(area.top() + self.MARGEN, y))

    # ------------------------------------------------------------------ para las pruebas
    def skus(self) -> list[str]:
        """Los SKU visibles, en el orden de las tarjetas."""
        return [tarjeta.sku for tarjeta in self._tarjetas]

    def tarjetas(self) -> list[_TarjetaNuevoSku]:
        return list(self._tarjetas)

    def ocultos(self) -> str:
        """El texto del enlace «N ocultos · mostrar» (cadena vacía si no hay tarjetas cerradas)."""
        return self.btn_ocultos.text() if self.btn_ocultos is not None else ""

    def mas(self) -> str:
        """El «+N más» visible (cadena vacía si no hay más de 3 SKU)."""
        return self.lbl_mas.text() if self.lbl_mas is not None and self.lbl_mas.isVisible() else ""

    # ------------------------------------------------------------------ pintura
    def _limpiar_tarjetas(self) -> None:
        while self._en_aviso.count():
            item = self._en_aviso.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._tarjetas = []
        self.lbl_mas = None
        self.btn_ocultos = None

    def _pintar(self, grupos: list[dict], ocultos: int = 0) -> None:
        self._limpiar_tarjetas()
        for grupo in grupos[:MAX_TARJETAS]:
            tarjeta = _TarjetaNuevoSku(grupo["sku"], _subtitulo(grupo))
            tarjeta.crear.connect(self.crear_solicitado.emit)
            tarjeta.descartar.connect(self.descartar_solicitado.emit)
            tarjeta.cerrar.connect(self.cerrar_sku)
            self._en_aviso.addWidget(tarjeta)
            self._tarjetas.append(tarjeta)
        restantes = len(grupos) - MAX_TARJETAS
        if restantes > 0:
            self.lbl_mas = QLabel(t("+{n} más", n=restantes))
            self.lbl_mas.setObjectName("masAviso")
            self._en_aviso.addWidget(self.lbl_mas)
        if ocultos:
            texto = t("1 oculto · mostrar") if ocultos == 1 else t("{n} ocultos · mostrar", n=ocultos)
            self.btn_ocultos = QPushButton(texto)
            self.btn_ocultos.setObjectName("ocultosAviso")
            self.btn_ocultos.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_ocultos.clicked.connect(self.mostrar_ocultos)
            self._en_aviso.addWidget(self.btn_ocultos, 0, Qt.AlignmentFlag.AlignRight)

    def _aplicar_estilo(self) -> None:
        self.setStyleSheet(_estilo(colores()))


class DialogoNuevoSku(QDialog):
    """Pide nombre y categoría para crear el SKU del aviso; el SKU va en solo lectura y en mayúsculas."""

    def __init__(self, sku: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("Crear y procesar"))
        self.setMinimumWidth(440)
        self.txt_sku = QLineEdit(_normalizar(sku))
        self.txt_sku.setReadOnly(True)
        self.txt_sku.setToolTip(t("El SKU viene en la lectura; no se puede cambiar."))
        self.txt_nombre = QLineEdit()
        self.txt_nombre.setPlaceholderText(t("Nombre del producto"))
        self.txt_categoria = QLineEdit()
        self.txt_categoria.setPlaceholderText(t("Categoría"))
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorFormulario")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        ayuda = QLabel(t("El SKU no está en el catálogo. Al crearlo se le asigna stock 0 y la lectura se procesa."))
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        forma = QFormLayout()
        forma.addRow(t("SKU"), self.txt_sku)
        forma.addRow(t("Nombre del producto"), self.txt_nombre)
        forma.addRow(t("Categoría"), self.txt_categoria)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.button(QDialogButtonBox.StandardButton.Ok).setText(t("Crear y procesar"))
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText(t("Cancelar"))
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(18, 16, 18, 14)
        raiz.setSpacing(10)
        raiz.addWidget(ayuda)
        raiz.addLayout(forma)
        raiz.addWidget(self.lbl_error)
        raiz.addWidget(botones)

    def datos(self) -> tuple[str, str, str]:
        return self.txt_sku.text().strip().upper(), self.txt_nombre.text().strip(), self.txt_categoria.text().strip()

    def _aceptar(self) -> None:
        _sku, nombre, categoria = self.datos()
        if not nombre or not categoria:
            self.lbl_error.setText(t("El nombre y la categoría son obligatorios."))
            self.lbl_error.show()
            return
        self.accept()
