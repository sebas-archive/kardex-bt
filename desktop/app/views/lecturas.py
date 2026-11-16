"""Ventana «Lecturas de un producto» (doble clic en una fila de Inventario).

Encabezado con el producto, resumen en indicadores compactos, tabla refinada (estado «vigente» como etiqueta,
miniatura de la foto y menú contextual) y un estado vacío cuando el producto no tiene lecturas. Los datos son los de
``db.fetch_lecturas``; las fotos, las de la carpeta de fotos del PC. No hay ninguna operación nueva.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QStackedLayout,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import db, tema
from ..i18n import registrar, t
from ..models import Lectura, fmt_num
from .base import QueryRunner, StateBanner
from .capas import abrir_capa, superficie
from .foto import leer_foto
from .iconos import icono
from . import motion, motion_global
from .visor_foto import FotoLectura, ver_fotos

registrar({
    "Lecturas de {sku} — {nombre}": "Readings for {sku} — {nombre}",
    "Sin lecturas para este SKU": "No readings for this SKU",
    "Todavía no hay lecturas": "No readings yet",
    "Las lecturas aparecen aquí cuando un operador cuenta este producto con la app del celular.":
        "Readings appear here once an operator counts this product with the phone app.",
    "{n} lecturas": "{n} readings",
    "1 lectura": "1 reading",
    "Contado": "Counted",
    "Sin contar": "Not counted",
    "Total de lecturas": "Total readings",
    "Cantidad vigente": "Current quantity",
    "No vigentes": "Not current",
    "Última lectura": "Latest reading",
    "No vigente": "Not current",
    "Sin foto": "No photo",
    "Ver fotografía": "View photo",
    "Ver detalles de la lectura": "View reading details",
    "Consultar nota": "View note",
    "Detalles de la lectura": "Reading details",
    "Foto": "Photo",
    "La foto no está disponible": "The photo is not available",
    "Cerrar": "Close",
    "Fecha": "Date",
    "Sin nota": "No note",
})

COLUMNAS = ("Cantidad", "Operador", "Fecha (UTC)", "Vigente", "Nota", "Foto")
COL_CANTIDAD, COL_OPERADOR, COL_FECHA, COL_VIGENTE, COL_NOTA, COL_FOTO = range(6)
ALTO_FILA = 52
MINI = QSize(48, 36)


def _mix(a: str, b: str, k: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * k), round(ca.green() + (cb.green() - ca.green()) * k),
                  round(ca.blue() + (cb.blue() - ca.blue()) * k))


def _qss(c: dict[str, str]) -> str:
    return f"""
    QWidget#lecturas {{ background: transparent; }}
    QLabel#lecTitulo {{ font-size: 21px; font-weight: 700; color: {c['texto_fuerte']}; background: transparent; }}
    QLabel#lecSub {{ font-size: 13px; color: {c['texto_suave']}; background: transparent; }}
    QLabel#lecSku {{ font-size: 12px; font-weight: 700; color: {c['texto_tenue']}; background: {c['tarjeta_alt']};
        border: 1px solid {c['borde']}; border-radius: 7px; padding: 2px 8px; }}
    QFrame#lecTarjeta {{ background: {c['tarjeta_alt']}; border: 1px solid {c['borde']}; border-radius: 14px; }}
    QLabel#lecCifra {{ font-size: 19px; font-weight: 700; color: {c['texto_fuerte']}; background: transparent; }}
    QLabel#lecCifraSuave {{ font-size: 15px; font-weight: 700; color: {c['texto_fuerte']}; background: transparent; }}
    QLabel#lecLeyenda {{ font-size: 11px; color: {c['texto_suave']}; background: transparent; }}
    QFrame#lecTabla {{ background: transparent; border: 1px solid {c['borde']}; border-radius: 14px; }}
    QPushButton#lecX {{ background: transparent; border: none; border-radius: 15px; min-width: 30px; max-width: 30px;
        min-height: 30px; max-height: 30px; padding: 0; }}
    QPushButton#lecX:hover {{ background: {c['tarjeta_alt']}; }}
    QPushButton#lecX:pressed {{ background: {c['borde']}; }}
    QTableWidget#lecLista {{ background: transparent; border: none; outline: 0; gridline-color: transparent; }}
    QTableWidget#lecLista QHeaderView {{ background: transparent; }}
    QTableWidget#lecLista QHeaderView::section {{ background: transparent; color: {c['texto_suave']}; border: none;
        border-bottom: 1px solid {c['borde']}; padding: 11px 14px; font-size: 11px; font-weight: 700; }}
    QTableWidget#lecLista QScrollBar:vertical {{ width: 10px; background: transparent; margin: 4px 2px; }}
    QTableWidget#lecLista QScrollBar::handle:vertical {{ background: {c['borde_fuerte']}; border-radius: 3px; min-height: 30px; }}
    QTableWidget#lecLista QScrollBar::add-line, QTableWidget#lecLista QScrollBar::sub-line {{ height: 0; }}
    QLabel#lecVacioTitulo {{ font-size: 18px; font-weight: 700; color: {c['texto_fuerte']}; background: transparent; }}
    QLabel#lecVacioTexto {{ font-size: 13px; color: {c['texto_suave']}; background: transparent; }}
    QPushButton#lecMini {{ background: {c['tarjeta_alt']}; border: 1px solid {c['borde']}; border-radius: 8px; padding: 0; }}
    QPushButton#lecMini:hover {{ border-color: {c['acento']}; }}
    QPushButton#lecCerrar {{ background: {c['tarjeta']}; border: 1px solid {c['borde_fuerte']}; border-radius: 9px;
        padding: 7px 18px; color: {c['texto']}; font-weight: 600; }}
    QPushButton#lecCerrar:hover {{ background: {c['tarjeta_alt']}; }}
    """


# ------------------------------------------------------------------ piezas
class _Indicador(QFrame):
    """Tarjeta compacta: icono discreto, cifra destacada y leyenda."""

    def __init__(self, icono_id: str, leyenda: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("lecTarjeta")
        c = tema.colores()
        chip = QLabel()
        chip.setFixedSize(34, 34)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setPixmap(icono(icono_id, color=color, tam=18).pixmap(18, 18))
        fondo = QColor(color)
        fondo.setAlphaF(0.14)
        chip.setStyleSheet(f"background: rgba({fondo.red()},{fondo.green()},{fondo.blue()},0.14); border-radius: 10px;")
        self.cifra = QLabel("—")
        self.cifra.setObjectName("lecCifra")
        self.leyenda = QLabel(leyenda)
        self.leyenda.setObjectName("lecLeyenda")
        textos = QVBoxLayout()
        textos.setSpacing(0)
        textos.addWidget(self.cifra)
        textos.addWidget(self.leyenda)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(12)
        lay.addWidget(chip)
        lay.addLayout(textos, 1)
        self.setMinimumHeight(62)
        self._c = c

    def poner(self, texto: str, compacto: bool = False) -> None:
        self.cifra.setObjectName("lecCifraSuave" if compacto else "lecCifra")
        self.cifra.style().unpolish(self.cifra)
        self.cifra.style().polish(self.cifra)
        motion.cruzar_texto(self.cifra, texto, 200)


class _Etiqueta(QLabel):
    """Pastilla de estado (producto contado / sin contar) del encabezado."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hide()

    def poner(self, texto: str, color: str) -> None:
        q = QColor(color)
        self.setText(f"●  {texto}")
        self.setStyleSheet(f"background: rgba({q.red()},{q.green()},{q.blue()},0.14); color: {color}; "
                           f"border-radius: 10px; padding: 4px 14px; font-size: 12px; font-weight: 700;")
        self.show()


class _Vacio(QWidget):
    """Estado vacío: icono, mensaje y una frase corta. Sin botón: el escritorio no registra lecturas."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        c = tema.colores()
        disco = QLabel()
        disco.setFixedSize(76, 76)
        disco.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disco.setPixmap(icono("lista", color=c["texto_suave"], tam=32).pixmap(32, 32))
        disco.setStyleSheet(f"background: {c['tarjeta_alt']}; border: 1px solid {c['borde']}; border-radius: 38px;")
        titulo = QLabel(t("Todavía no hay lecturas"))
        titulo.setObjectName("lecVacioTitulo")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        texto = QLabel(t("Las lecturas aparecen aquí cuando un operador cuenta este producto con la app del celular."))
        texto.setObjectName("lecVacioTexto")
        texto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        texto.setWordWrap(True)
        texto.setFixedWidth(380)
        texto.setMinimumHeight(40)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        lay.addWidget(disco, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(14)
        lay.addWidget(titulo)
        lay.addWidget(texto, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(2)


class _Tabla(QTableWidget):
    """Tabla que sabe cuál fila tiene el cursor (para el resalte suave)."""

    def __init__(self, filas: int, columnas: int) -> None:
        super().__init__(filas, columnas)
        self.fila_hover = -1
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def mouseMoveEvent(self, evento) -> None:
        fila = self.rowAt(round(evento.position().y()))
        if fila != self.fila_hover:
            self.fila_hover = fila
            self.viewport().update()
        super().mouseMoveEvent(evento)

    def leaveEvent(self, evento) -> None:
        if self.fila_hover != -1:
            self.fila_hover = -1
            self.viewport().update()
        super().leaveEvent(evento)


class _Delegado(QStyledItemDelegate):
    """Dibuja las filas: resalte al pasar y al seleccionar, separador sutil, etiqueta «Vigente» y «sin foto»."""

    def __init__(self, tabla: _Tabla) -> None:
        super().__init__(tabla)
        self._tabla = tabla
        self.c = tema.colores()

    def paint(self, p: QPainter, option, index) -> None:
        c = self.c
        fila, col = index.row(), index.column()
        r = QRectF(option.rect)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        seleccionada = bool(option.state & QStyle.StateFlag.State_Selected)
        if seleccionada:
            p.fillRect(option.rect, QColor(c["seleccion"]))
            if col == 0:
                p.fillRect(QRectF(r.left(), r.top() + 10, 3, r.height() - 20), QColor(c["acento"]))
        elif fila == self._tabla.fila_hover:
            p.fillRect(option.rect, QColor(c["tarjeta_alt"]))
        sep = QColor(c["borde"])
        sep.setAlphaF(0.7)
        p.setPen(QPen(sep, 1))
        p.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())

        vigente = bool(index.data(Qt.ItemDataRole.UserRole))
        if col == COL_VIGENTE:
            self._etiqueta(p, r, vigente)
        elif col == COL_FOTO:
            if self._tabla.cellWidget(fila, col) is None:
                self._sin_foto(p, r)
        else:
            texto = index.data(Qt.ItemDataRole.DisplayRole) or ""
            fuente = QFont(option.font)
            fuente.setPixelSize(13)
            if col == COL_CANTIDAD:
                fuente.setPixelSize(15)
                fuente.setWeight(QFont.Weight.DemiBold)
            p.setFont(fuente)
            color = c["texto_fuerte"] if vigente else c["texto_suave"]
            if col in (COL_OPERADOR, COL_FECHA, COL_NOTA) and vigente:
                color = c["texto"]
            if col == COL_NOTA and not texto:
                color = c["texto_suave"]
            p.setPen(QColor(color))
            area = r.adjusted(14, 0, -14, 0)
            alinear = Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignRight if col == COL_CANTIDAD
                                                       else Qt.AlignmentFlag.AlignLeft)
            p.drawText(area, int(alinear), p.fontMetrics().elidedText(str(texto), Qt.TextElideMode.ElideRight,
                                                                      int(area.width())))
        p.restore()

    def _etiqueta(self, p: QPainter, r: QRectF, vigente: bool) -> None:
        c = self.c
        color = QColor(c["acento"] if vigente else c["texto_suave"])
        texto = t("Vigente") if vigente else t("No vigente")
        fuente = QFont(p.font())
        fuente.setPixelSize(12)
        fuente.setWeight(QFont.Weight.DemiBold)
        p.setFont(fuente)
        ancho = p.fontMetrics().horizontalAdvance(texto) + 34
        caja = QRectF(r.left() + 14, r.center().y() - 12, ancho, 24)
        fondo = QColor(color)
        fondo.setAlphaF(0.14)
        ruta = QPainterPath()
        ruta.addRoundedRect(caja, 12, 12)
        p.fillPath(ruta, fondo)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPoint(round(caja.left() + 13), round(caja.center().y())), 3, 3)
        p.setPen(color)
        p.drawText(QRectF(caja.left() + 22, caja.top(), caja.width() - 24, caja.height()),
                   int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), texto)

    def _sin_foto(self, p: QPainter, r: QRectF) -> None:
        mapa = icono("sin_imagen", color=self.c["texto_suave"], tam=16).pixmap(16, 16)
        p.setOpacity(0.55)
        p.drawPixmap(round(r.left() + 14), round(r.center().y() - 8), mapa)
        p.setOpacity(1.0)

    def sizeHint(self, option, index) -> QSize:
        col = index.column()
        if col in (COL_VIGENTE, COL_FOTO):
            return QSize(0, ALTO_FILA)
        fuente = QFont(option.font)
        fuente.setPixelSize(15 if col == COL_CANTIDAD else 13)
        if col == COL_CANTIDAD:
            fuente.setWeight(QFont.Weight.DemiBold)
        ancho = QFontMetrics(fuente).horizontalAdvance(str(index.data(Qt.ItemDataRole.DisplayRole) or ""))
        return QSize(ancho + 32, ALTO_FILA)


# ------------------------------------------------------------------ detalle de una lectura
class DetalleLectura(QWidget):
    """Todos los datos de una lectura (también su nota completa). Panel para una capa flotante."""

    cerrar_pedido = pyqtSignal()

    def __init__(self, lectura: Lectura, producto: str, sku: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        c = tema.colores()
        self.setObjectName("detalleLectura")
        self.setMinimumWidth(380)
        self._c = c
        self.setStyleSheet(f"""
            QWidget#detalleLectura {{ background: transparent; }}
            QLabel {{ background: transparent; color: {c['texto']}; font-size: 13px; }}
            QLabel#dEtiqueta {{ color: {c['texto_suave']}; font-size: 10px; font-weight: 700; }}
            QLabel#dTitulo {{ color: {c['texto_fuerte']}; font-size: 17px; font-weight: 700; }}""")
        rejilla = QGridLayout()
        rejilla.setVerticalSpacing(2)
        titulo = QLabel(f"{producto}")
        titulo.setObjectName("dTitulo")
        titulo.setWordWrap(True)
        filas = (("SKU", sku), ("Cantidad", fmt_num(lectura.cantidad)), ("Operador", lectura.operador or "—"),
                 ("Fecha (UTC)", lectura.fecha_captura.strftime("%Y-%m-%d %H:%M:%S")),
                 ("Vigente", t("Sí") if lectura.vigente else t("No")), ("Nota", lectura.nota or t("Sin nota")))
        fila = 0
        self.valores: dict[str, QLabel] = {}
        for etiqueta, valor in filas:
            e = QLabel(t(etiqueta).upper())
            e.setObjectName("dEtiqueta")
            v = QLabel(valor)
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            rejilla.addWidget(e, fila, 0)
            rejilla.addWidget(v, fila + 1, 0)
            rejilla.setRowMinimumHeight(fila + 2, 8)
            self.valores[etiqueta] = v
            fila += 3
        cerrar = QPushButton(t("Cerrar"))
        cerrar.setObjectName("lecCerrar")
        cerrar.setStyleSheet(_qss(c))
        cerrar.clicked.connect(lambda: self.cerrar_pedido.emit())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(titulo)
        lay.addLayout(rejilla)
        lay.addWidget(cerrar, 0, Qt.AlignmentFlag.AlignRight)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        superficie(p, QRectF(self.rect()), self._c["tarjeta"], self._c["borde"], 16)


# ------------------------------------------------------------------ ventana
class DetalleLecturas(QWidget):
    """Todas las lecturas de un SKU, marcando cuál es la vigente (la más reciente).

    Es el panel de una capa flotante (``capas.CapaFlotante``): no es una ventana del sistema. Los datos, la
    selección y el desplazamiento de la tabla se conservan mientras haya otra capa (el visor) encima."""

    cerrar_pedido = pyqtSignal()

    def __init__(self, sku: str, nombre: str, parent: QWidget | None = None, categoria: str = "",
                 contada: float | None = None, sistema: float | None = None) -> None:
        super().__init__(parent)
        self._sku, self._nombre, self._categoria = sku, nombre, categoria
        self._lecturas: list[Lectura] = []
        self._miniaturas: dict[int, QPixmap] = {}
        self._popup: QWidget | None = None
        self._capa_popup = None
        c = tema.colores()
        self.setObjectName("lecturas")
        self.setWindowTitle(t("Lecturas de {sku} — {nombre}", sku=sku, nombre=nombre))
        self.setStyleSheet(_qss(c))
        self.setMinimumSize(560, 380)
        self._c = c
        self._runner = QueryRunner(self)

        # ------------------------------------------------------------ encabezado
        self.lbl_nombre = QLabel(nombre)
        self.lbl_nombre.setObjectName("lecTitulo")
        self.lbl_nombre.setWordWrap(True)
        self.lbl_sku = QLabel(f"SKU {sku}")
        self.lbl_sku.setObjectName("lecSku")
        self.lbl_categoria = QLabel(t(categoria) if categoria else "")
        self.lbl_categoria.setObjectName("lecSub")
        self.lbl_cuenta = QLabel("")
        self.lbl_cuenta.setObjectName("lecSub")
        meta = QHBoxLayout()
        meta.setSpacing(10)
        meta.addWidget(self.lbl_sku)
        meta.addWidget(self.lbl_categoria)
        meta.addWidget(self.lbl_cuenta)
        meta.addStretch(1)
        izquierda = QVBoxLayout()
        izquierda.setSpacing(6)
        izquierda.addWidget(self.lbl_nombre)
        izquierda.addLayout(meta)
        self.estado = _Etiqueta()
        self.btn_cerrar = QPushButton()
        self.btn_cerrar.setObjectName("lecX")
        self.btn_cerrar.setIcon(icono("cerrar", color=c["texto_suave"], color_activo=c["texto_fuerte"], tam=16))
        self.btn_cerrar.setIconSize(QSize(16, 16))
        self.btn_cerrar.setToolTip(t("Cerrar"))
        self.btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cerrar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_cerrar.clicked.connect(lambda: self.cerrar_pedido.emit())
        cabecera = QHBoxLayout()
        cabecera.setSpacing(10)
        cabecera.addLayout(izquierda, 1)
        cabecera.addWidget(self.estado, 0, Qt.AlignmentFlag.AlignTop)
        cabecera.addWidget(self.btn_cerrar, 0, Qt.AlignmentFlag.AlignTop)

        # ------------------------------------------------------------ indicadores
        self.ind_total = _Indicador("lista", t("Total de lecturas"), c["info"])
        self.ind_vigente = _Indicador("check_circulo", t("Cantidad vigente"), c["acento"])
        self.ind_no_vigentes = _Indicador("capas", t("No vigentes"), c["texto_suave"])
        self.ind_ultima = _Indicador("reloj", t("Última lectura"), c["aviso"])
        indicadores = QHBoxLayout()
        indicadores.setSpacing(12)
        for ind in (self.ind_total, self.ind_vigente, self.ind_no_vigentes, self.ind_ultima):
            indicadores.addWidget(ind, 1)
        self._indicadores = indicadores

        # ------------------------------------------------------------ tabla / vacío
        self.banner = StateBanner()
        self.banner.retry.connect(lambda: self._cargar(self._sku))
        self.tabla = _Tabla(0, 6)
        self.tabla.setObjectName("lecLista")
        self.tabla.setHorizontalHeaderLabels([t(x) for x in COLUMNAS])
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setShowGrid(False)
        self.tabla.setFrameShape(QFrame.Shape.NoFrame)
        self.tabla.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabla.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(ALTO_FILA)
        cab = self.tabla.horizontalHeader()
        cab.setHighlightSections(False)
        cab.setSectionsClickable(False)
        cab.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        cab.setSectionResizeMode(COL_CANTIDAD, QHeaderView.ResizeMode.Fixed)
        cab.setSectionResizeMode(COL_OPERADOR, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_FECHA, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_VIGENTE, QHeaderView.ResizeMode.Fixed)
        cab.setSectionResizeMode(COL_NOTA, QHeaderView.ResizeMode.Stretch)
        cab.setSectionResizeMode(COL_FOTO, QHeaderView.ResizeMode.Fixed)
        self.tabla.setColumnWidth(COL_CANTIDAD, 110)
        self.tabla.setColumnWidth(COL_VIGENTE, 140)
        self.tabla.setColumnWidth(COL_FOTO, 84)
        self.tabla.setItemDelegate(_Delegado(self.tabla))
        self.tabla.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabla.customContextMenuRequested.connect(self._menu)
        self.tabla.doubleClicked.connect(lambda ix: self._abrir_fila(ix.row()))
        self.vacio = _Vacio()
        self._pila = QStackedLayout()
        self._pila.addWidget(self.tabla)
        self._pila.addWidget(self.vacio)
        self._marco = QFrame()
        self._marco.setObjectName("lecTabla")
        interior = QVBoxLayout(self._marco)
        interior.setContentsMargins(6, 4, 6, 6)
        interior.addLayout(self._pila)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 22, 26, 22)
        raiz.setSpacing(16)
        raiz.addLayout(cabecera)
        raiz.addLayout(indicadores)
        raiz.addWidget(self.banner)
        raiz.addWidget(self._marco, 1)
        self._poner_resumen([])
        self._cargar(sku)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        superficie(p, QRectF(self.rect()), self._c["tarjeta"], self._c["borde"], 18)

    def reject(self) -> None:
        self.cerrar_pedido.emit()

    # ------------------------------------------------------------- datos
    def _cargar(self, sku: str) -> None:
        self.banner.show_loading()
        self._runner.run(db.fetch_lecturas, self._mostrar, self._error, sku, key="lecturas")

    def _error(self, mensaje: str) -> None:
        self.banner.show_error(mensaje)

    def _poner_resumen(self, lecturas: list[Lectura]) -> None:
        c = tema.colores()
        n = len(lecturas)
        vigente = next((x for x in lecturas if x.vigente), None)
        self.ind_total.poner(str(n))
        self.ind_vigente.poner(fmt_num(vigente.cantidad) if vigente else "—")
        self.ind_no_vigentes.poner(str(sum(1 for x in lecturas if not x.vigente)))
        if lecturas:
            ultima = max(x.fecha_captura for x in lecturas)
            self.ind_ultima.poner(ultima.strftime("%Y-%m-%d"), compacto=True)
            self.ind_ultima.setToolTip(f"{ultima:%Y-%m-%d %H:%M:%S} UTC")
            self.lbl_cuenta.setText(("· " + t("1 lectura")) if n == 1 else "· " + t("{n} lecturas", n=n))
        else:
            self.ind_ultima.poner("—")
            self.ind_ultima.leyenda.setText(t("Última lectura"))
            self.lbl_cuenta.setText("· " + t("{n} lecturas", n=0))
        self.lbl_categoria.setVisible(bool(self._categoria))
        if vigente:
            self.estado.poner(t("Contado"), c["acento"])
        else:
            self.estado.poner(t("Sin contar"), c["texto_suave"])
        self.estado.setVisible(True)

    def _mostrar(self, lecturas: list[Lectura]) -> None:
        self._lecturas = list(lecturas)
        self._miniaturas.clear()
        self.banner.clear()
        self._poner_resumen(self._lecturas)
        if not lecturas:
            self._pila.setCurrentWidget(self.vacio)
            self.tabla.setRowCount(0)
            return
        self._pila.setCurrentWidget(self.tabla)
        seleccion = self.tabla.currentRow()
        self.tabla.setRowCount(len(lecturas))
        for fila, lectura in enumerate(lecturas):
            celdas = (
                fmt_num(lectura.cantidad),
                lectura.operador or "—",
                lectura.fecha_captura.strftime("%Y-%m-%d %H:%M:%S"),
                t("Sí") if lectura.vigente else t("No"),
                lectura.nota or "",
            )
            for columna, texto in enumerate(celdas):
                item = QTableWidgetItem(texto)
                item.setData(Qt.ItemDataRole.UserRole, lectura.vigente)
                if columna == COL_CANTIDAD:
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
                if lectura.nota and columna == COL_NOTA:
                    item.setToolTip(lectura.nota)
                self.tabla.setItem(fila, columna, item)
            foto_item = QTableWidgetItem("")
            foto_item.setData(Qt.ItemDataRole.UserRole, lectura.vigente)
            self.tabla.setItem(fila, COL_FOTO, foto_item)
            if lectura.ruta_foto:
                self.tabla.setCellWidget(fila, COL_FOTO, self._boton_foto(fila, lectura))
        # Operador y fecha toman lo que necesitan; la nota, el resto.
        if 0 <= seleccion < len(lecturas):
            self.tabla.selectRow(seleccion)
        # Las lecturas llegan tras abrirse el panel: sus filas se revelan en cascada (los datos ya están completos debajo).
        claves = [str(i) for i in range(len(lecturas))]
        motion_global.entrada_filas(self.tabla, claves, claves)

    # ------------------------------------------------------------- fotos y miniaturas
    def _boton_foto(self, fila: int, lectura: Lectura) -> QWidget:
        envoltorio = QWidget()
        envoltorio.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        boton = QPushButton()
        boton.setObjectName("lecMini")
        boton.setFixedSize(MINI)
        boton.setCursor(Qt.CursorShape.PointingHandCursor)
        boton.setToolTip(t("Ver foto"))
        boton.setIcon(icono("imagen", color=tema.colores()["texto_suave"], tam=16))
        boton.setIconSize(QSize(16, 16))
        boton.clicked.connect(lambda _c=False, f=fila, b=boton: self._abrir_visor_en(f, b))
        lay = QHBoxLayout(envoltorio)
        lay.setContentsMargins(14, 0, 0, 0)
        lay.addWidget(boton, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addStretch(1)
        self._runner.run(leer_foto, lambda datos, b=boton, f=fila: self._miniatura(b, f, datos),
                         lambda m, b=boton: self._sin_miniatura(b, m), lectura.ruta_foto)
        envoltorio.boton = boton   # para pruebas y para el origen de la animación
        return envoltorio

    def _miniatura(self, boton: QPushButton, fila: int, datos: bytes) -> None:
        mapa = QPixmap()
        if not mapa.loadFromData(datos):
            return self._sin_miniatura(boton, t("El archivo no es una imagen válida."))
        dpr = 2
        mini = mapa.scaled(MINI.width() * dpr - 4, MINI.height() * dpr - 4, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
        x, y = (mini.width() - (MINI.width() * dpr - 4)) // 2, (mini.height() - (MINI.height() * dpr - 4)) // 2
        mini = mini.copy(x, y, MINI.width() * dpr - 4, MINI.height() * dpr - 4)
        redonda = QPixmap(mini.size())
        redonda.fill(Qt.GlobalColor.transparent)
        p = QPainter(redonda)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ruta = QPainterPath()
        ruta.addRoundedRect(QRectF(0, 0, mini.width(), mini.height()), 12, 12)
        p.setClipPath(ruta)
        p.drawPixmap(0, 0, mini)
        p.end()
        redonda.setDevicePixelRatio(dpr)
        self._miniaturas[fila] = redonda
        try:
            boton.setIcon(QIcon(redonda))
            boton.setIconSize(QSize(MINI.width() - 2, MINI.height() - 2))
        except RuntimeError:
            pass

    def _sin_miniatura(self, boton: QPushButton, mensaje: str) -> None:
        try:
            boton.setIcon(icono("sin_imagen", color=tema.colores()["error"], tam=16))
            boton.setToolTip(mensaje)
        except RuntimeError:
            pass

    def _fotos(self) -> tuple[list[FotoLectura], dict[int, int]]:
        """Las fotos navegables (solo las que existen) y de qué fila viene cada una."""
        fotos, por_fila = [], {}
        for fila, x in enumerate(self._lecturas):
            if x.ruta_foto:
                por_fila[fila] = len(fotos)
                fotos.append(FotoLectura(
                    ruta=x.ruta_foto, producto=self._nombre, sku=self._sku, cantidad=fmt_num(x.cantidad),
                    operador=x.operador or "", fecha=x.fecha_captura.strftime("%Y-%m-%d %H:%M:%S"),
                    nota=x.nota or ""))
        return fotos, por_fila

    def _abrir_visor_en(self, fila: int, boton: QWidget | None = None) -> None:
        fotos, por_fila = self._fotos()
        if fila not in por_fila:
            return
        origen = None
        if boton is not None:
            esq = boton.mapToGlobal(QPoint(0, 0))
            origen = QRect(esq, boton.size())
        filas = {v: k for k, v in por_fila.items()}
        self.tabla.selectRow(fila)
        ver_fotos(self, fotos, por_fila[fila], origen, lambda i: self.tabla.selectRow(filas[i]))

    def _abrir_fila(self, fila: int) -> None:
        if not 0 <= fila < len(self._lecturas):
            return
        if self._lecturas[fila].ruta_foto:
            envoltorio = self.tabla.cellWidget(fila, COL_FOTO)
            self._abrir_visor_en(fila, getattr(envoltorio, "boton", None))
        else:
            self.ver_detalles(fila)

    # ------------------------------------------------------------- acciones de fila
    def ver_detalles(self, fila: int) -> None:
        if not 0 <= fila < len(self._lecturas):
            return
        self._popup = DetalleLectura(self._lecturas[fila], self._nombre, self._sku)
        ventana = self.window()
        if ventana is self:       # sin ventana principal (pruebas de la vista sola): queda como widget suelto
            self._popup.show()
            return
        self._capa_popup = abrir_capa(ventana, self._popup, area="ventana", oscuridad=0.34, radio=16,
                                      tamano=lambda a: QSize(min(460, a.width() - 40), self._popup.sizeHint().height()))

    def _menu(self, pos) -> None:
        fila = self.tabla.rowAt(pos.y())
        if not 0 <= fila < len(self._lecturas):
            return
        self.tabla.selectRow(fila)
        lectura = self._lecturas[fila]
        menu = QMenu(self)
        if lectura.ruta_foto:
            menu.addAction(icono("imagen"), t("Ver fotografía"), lambda: self._abrir_fila(fila))
        menu.addAction(icono("lista"), t("Ver detalles de la lectura"), lambda: self.ver_detalles(fila))
        if lectura.nota:
            menu.addAction(icono("Notificaciones"), t("Consultar nota"), lambda: self.ver_detalles(fila))
        menu.exec(self.tabla.viewport().mapToGlobal(pos))

    def keyPressEvent(self, evento) -> None:
        if evento.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.tabla.currentRow() >= 0:
            self._abrir_fila(self.tabla.currentRow())
            return
        super().keyPressEvent(evento)
