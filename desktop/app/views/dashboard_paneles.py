"""Paneles flotantes de la personalización del dashboard: catálogo de widgets y configuración de un gráfico.

Son hojas sobre la ventana (no ventanas aparte): fondo atenuado, tarjeta centrada, se cierran con Esc o pulsando
fuera. Las vistas previas del catálogo son pictogramas del tipo de visualización, nunca datos inventados.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QDate, QEvent, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QScrollArea, QSpinBox, QToolButton, QVBoxLayout, QWidget)

from .. import dashboard_prefs as prefs
from ..dashboard_datos import Datos
from ..i18n import registrar, t
from ..tema import colores
from .grafico_personal import GraficoPersonal
from .isla import isla

registrar({
    "Agregar widget": "Add widget", "Catálogo de widgets": "Widget catalog", "Todos": "All", "Agregar": "Add",
    "Ya agregado": "Already added", "Listo": "Done", "Configurar gráfico": "Configure chart",
    "Nombre del gráfico": "Chart name", "Fuente de datos": "Data source", "Visualización": "Visualization",
    "Período": "Period", "Desde": "From", "Hasta": "To", "Agrupación": "Grouping", "Orden": "Order",
    "Elementos mostrados": "Items shown", "Todos los elementos": "All items", "Mostrar leyenda": "Show legend",
    "Mostrar valores": "Show values", "Tamaño": "Size", "Vista previa": "Preview",
    "Widget agregado": "Widget added", "Sin datos en este período": "No data in this period",
    "Indicador": "Indicator", "Panel": "Panel", "Gráfico": "Chart", "Total": "Total", "Diferencia": "Difference",
    "Avance": "Progress", "Lecturas": "Readings", "Dañados": "Damaged", "Productos": "Products",
    "Contados": "Counted", "Pendientes": "Pending", "Procesadas": "Processed", "Con error": "With error", "u.": "u.",
})

CATEGORICAS = {"dif_categoria", "avance_categoria", "lecturas_categoria", "danados", "operador"}


class Hoja(QWidget):
    """Base: velo sobre la ventana y una tarjeta centrada."""

    cerrada = pyqtSignal()

    def __init__(self, ventana: QWidget, ancho: int, alto: int) -> None:
        super().__init__(ventana)
        self._ventana = ventana
        self._ancho, self._alto = ancho, alto
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.caja = QFrame(self)
        self.caja.setObjectName("modalCaja")
        self.cuerpo = QVBoxLayout(self.caja)
        self.cuerpo.setContentsMargins(24, 20, 24, 20)
        self.cuerpo.setSpacing(14)
        ventana.installEventFilter(self)
        self.hide()

    def abrir(self) -> None:
        self._reubicar()
        self.show()
        self.raise_()
        self.setFocus()
        isla.elevar()

    def cerrar(self) -> None:
        if self.isVisible():
            self.hide()
            self.cerrada.emit()

    def _reubicar(self) -> None:
        self.setGeometry(self._ventana.rect())
        w = min(self._ancho, max(420, self.width() - 60))
        h = min(self._alto, max(320, self.height() - 60))
        self.caja.setGeometry(QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h).toRect())

    def eventFilter(self, objeto, evento) -> bool:
        if objeto is self._ventana and evento.type() == QEvent.Type.Resize and self.isVisible():
            self._reubicar()
        return super().eventFilter(objeto, evento)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        p.end()

    def mousePressEvent(self, evento) -> None:
        if not self.caja.geometry().contains(evento.position().toPoint()):
            self.cerrar()
        evento.accept()

    def keyPressEvent(self, evento) -> None:
        if evento.key() == Qt.Key.Key_Escape:
            self.cerrar()
            return
        super().keyPressEvent(evento)

    def _cabecera(self, titulo: str, subtitulo: str = "") -> None:
        fila = QVBoxLayout()
        fila.setSpacing(2)
        encabezado = QLabel(titulo)
        encabezado.setObjectName("modalTitulo")
        fila.addWidget(encabezado)
        if subtitulo:
            sub = QLabel(subtitulo)
            sub.setObjectName("ayuda")
            sub.setWordWrap(True)
            fila.addWidget(sub)
        self.cuerpo.addLayout(fila)


# ----------------------------------------------------------------------------- pictogramas
class Pictograma(QWidget):
    """Dibujo esquemático de un widget o de un tipo de gráfico (sin datos)."""

    def __init__(self, clase: str, ancho: int = 84, alto: int = 56, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._clase = clase
        self.setFixedSize(ancho, alto)

    def paintEvent(self, _evento) -> None:
        c = colores()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        caja = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(c["borde"]), 1.0))
        p.setBrush(QColor(c["tarjeta_alt"]))
        p.drawRoundedRect(caja, 9, 9)
        acento, otro = QColor(c["acento"]), QColor(c["info"])
        suave = QColor(c["texto_tenue"])
        suave.setAlpha(120)
        x0, y0, w, h = caja.left() + 10, caja.top() + 9, caja.width() - 20, caja.height() - 18
        p.setPen(Qt.PenStyle.NoPen)
        k = self._clase
        if k == "kpi":
            p.setBrush(suave)
            p.drawRoundedRect(QRectF(x0, y0, w * 0.45, 5), 2.5, 2.5)
            p.setBrush(acento)
            p.drawRoundedRect(QRectF(x0, y0 + 14, w * 0.7, 13), 4, 4)
            p.setBrush(suave)
            p.drawRoundedRect(QRectF(x0, y0 + h - 6, w * 0.55, 4), 2, 2)
        elif k == "panel":
            for i in range(4):
                p.setBrush(acento if i == 0 else suave)
                p.drawRoundedRect(QRectF(x0, y0 + i * 9, w * (0.9 if i != 2 else 0.6), 4), 2, 2)
        elif k in ("barras", "comparativo", "apiladas"):
            alturas = (0.45, 0.8, 0.6, 0.95)
            for i, a in enumerate(alturas):
                bx = x0 + i * (w / 4) + 2
                if k == "apiladas":
                    p.setBrush(acento)
                    p.drawRoundedRect(QRectF(bx, y0 + h * (1 - a), w / 4 - 6, h * a * 0.6), 2, 2)
                    p.setBrush(otro)
                    p.drawRoundedRect(QRectF(bx, y0 + h * (1 - a * 0.4), w / 4 - 6, h * a * 0.4), 2, 2)
                elif k == "comparativo":
                    p.setBrush(acento)
                    p.drawRoundedRect(QRectF(bx, y0 + h * (1 - a), (w / 4 - 6) / 2, h * a), 1.5, 1.5)
                    p.setBrush(otro)
                    p.drawRoundedRect(QRectF(bx + (w / 4 - 6) / 2, y0 + h * (1 - a * 0.65), (w / 4 - 6) / 2, h * a * 0.65), 1.5, 1.5)
                else:
                    p.setBrush(acento)
                    p.drawRoundedRect(QRectF(bx, y0 + h * (1 - a), w / 4 - 6, h * a), 2, 2)
        elif k == "barras_h":
            for i, a in enumerate((0.9, 0.62, 0.8, 0.4)):
                p.setBrush(acento)
                p.drawRoundedRect(QRectF(x0, y0 + i * (h / 4) + 1, w * a, h / 4 - 4), 2, 2)
        elif k in ("lineas", "area", "evolucion"):
            puntos = [QPointF(x0 + w * f, y0 + h * (1 - v)) for f, v in ((0, 0.25), (0.3, 0.65), (0.6, 0.4), (1, 0.9))]
            linea = QPainterPath(puntos[0])
            for q in puntos[1:]:
                linea.lineTo(q)
            if k != "lineas":
                relleno = QPainterPath(linea)
                relleno.lineTo(QPointF(x0 + w, y0 + h))
                relleno.lineTo(QPointF(x0, y0 + h))
                relleno.closeSubpath()
                suave_a = QColor(acento)
                suave_a.setAlpha(60)
                p.fillPath(relleno, suave_a)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(acento, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(linea)
        elif k in ("circular", "anillo"):
            lado = min(w, h)
            centro = QPointF(caja.center().x(), caja.center().y())
            caja_c = QRectF(centro.x() - lado / 2, centro.y() - lado / 2, lado, lado)
            for ini, barrido, col in ((90, -150, acento), (-60, -110, otro), (-170, -100, QColor(c["aviso"]))):
                ruta = QPainterPath()
                ruta.moveTo(centro)
                ruta.arcTo(caja_c, ini, barrido)
                ruta.closeSubpath()
                p.setBrush(col)
                p.drawPath(ruta)
            if k == "anillo":
                p.setBrush(QColor(c["tarjeta_alt"]))
                p.drawEllipse(centro, lado * 0.27, lado * 0.27)
        p.end()


# ----------------------------------------------------------------------------- catálogo
class CatalogoWidgets(Hoja):
    """Los widgets disponibles, por categoría, con descripción, vista previa y si ya están en el dashboard."""

    agregar = pyqtSignal(str)

    def __init__(self, ventana: QWidget) -> None:
        super().__init__(ventana, 820, 600)
        self._sesion = None
        self._en_uso: set[str] = set()
        self._categoria = "Todos"
        self._cabecera(t("Catálogo de widgets"), t("Elige qué quieres ver en tu dashboard. Solo hay información real del sistema."))
        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(16)
        self._lista = QVBoxLayout()
        self._lista.setSpacing(2)
        self._botones: dict[str, QPushButton] = {}
        for nombre in ("Todos", *prefs.CATEGORIAS):
            b = QPushButton(t(nombre))
            b.setObjectName("categoriaCatalogo")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, n=nombre: self._elegir(n))
            self._botones[nombre] = b
            self._lista.addWidget(b)
        self._lista.addStretch(1)
        lateral = QWidget()
        lateral.setObjectName("hojaPanel")
        lateral.setFixedWidth(176)
        lateral.setLayout(self._lista)
        self._contenido = QVBoxLayout()
        self._contenido.setSpacing(10)
        interior = QWidget()
        interior.setObjectName("hojaPanel")
        interior.setLayout(self._contenido)
        self._scroll = QScrollArea()
        self._scroll.setObjectName("hojaScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidget(interior)
        cuerpo.addWidget(lateral)
        cuerpo.addWidget(self._scroll, 1)
        self.cuerpo.addLayout(cuerpo, 1)
        self.btn_listo = QPushButton(t("Listo"))
        self.btn_listo.setObjectName("primario")
        self.btn_listo.clicked.connect(self.cerrar)
        pie = QHBoxLayout()
        pie.addStretch(1)
        pie.addWidget(self.btn_listo)
        self.cuerpo.addLayout(pie)

    def abrir_con(self, sesion, en_uso: set[str]) -> None:
        self._sesion, self._en_uso = sesion, set(en_uso)
        self._pintar()
        self.abrir()

    def marcar_en_uso(self, clave: str) -> None:
        self._en_uso.add(clave)
        self._pintar()

    def _elegir(self, nombre: str) -> None:
        self._categoria = nombre
        self._pintar()

    def _pintar(self) -> None:
        for n, b in self._botones.items():
            b.setChecked(n == self._categoria)
        while self._contenido.count():
            item = self._contenido.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for d in prefs.CATALOGO:
            if not prefs.permitido(d, self._sesion):
                continue
            if self._categoria != "Todos" and d.categoria != self._categoria:
                continue
            self._contenido.addWidget(self._tarjeta(d))
        self._contenido.addStretch(1)

    def _tarjeta(self, d: prefs.Def) -> QFrame:
        marco = QFrame()
        marco.setObjectName("itemCatalogo")
        fila = QHBoxLayout(marco)
        fila.setContentsMargins(12, 10, 12, 10)
        fila.setSpacing(14)
        fila.addWidget(Pictograma(d.tipo_defecto if d.tipo == prefs.GRAFICO else d.tipo))
        texto = QVBoxLayout()
        texto.setSpacing(2)
        nombre = QLabel(t(d.nombre))
        nombre.setObjectName("seccion")
        desc = QLabel(t(d.descripcion))
        desc.setObjectName("ayuda")
        desc.setWordWrap(True)
        etiqueta = QLabel(f"{t(d.categoria)} · {t({'kpi': 'Indicador', 'panel': 'Panel', 'grafico': 'Gráfico'}[d.tipo])}")
        etiqueta.setObjectName("cardDetalle")
        texto.addWidget(nombre)
        texto.addWidget(desc)
        texto.addWidget(etiqueta)
        fila.addLayout(texto, 1)
        ya = d.unico and d.clave in self._en_uso
        boton = QPushButton(t("Ya agregado") if ya else t("Agregar"))
        boton.setEnabled(not ya)
        boton.setObjectName("primario" if not ya else "")
        boton.setCursor(Qt.CursorShape.PointingHandCursor)
        boton.clicked.connect(lambda _c=False, c=d.clave: self._pedir(c))
        fila.addWidget(boton, 0, Qt.AlignmentFlag.AlignVCenter)
        return marco

    def _pedir(self, clave: str) -> None:
        self.agregar.emit(clave)
        self.marcar_en_uso(clave)
        isla.exito(t("Widget agregado"), t(prefs.POR_CLAVE[clave].nombre))


# ----------------------------------------------------------------------------- configuración de un gráfico
class ConfigGrafico(Hoja):
    """Opciones de un gráfico. Los cambios se aplican al instante y se ven en la vista previa."""

    cambiado = pyqtSignal(str, str, dict, str)    # (id, clave de la fuente, opciones, tamaño)

    def __init__(self, ventana: QWidget, proveedor: Callable[[str, dict], Datos]) -> None:
        super().__init__(ventana, 900, 640)
        self._proveedor = proveedor
        self._id = ""
        self._cargando = False
        self._tipos: dict[str, QToolButton] = {}
        self._cabecera(t("Configurar gráfico"))
        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(20)
        forma = QFormLayout()
        forma.setVerticalSpacing(10)
        forma.setHorizontalSpacing(14)
        forma.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.txt_titulo = QLineEdit()
        self.cmb_fuente = QComboBox()
        for d in prefs.CATALOGO:
            if d.tipo == prefs.GRAFICO:
                self.cmb_fuente.addItem(t(d.nombre), d.clave)
        self.fila_tipos = QGridLayout()
        self.fila_tipos.setSpacing(6)
        contenedor_tipos = QWidget()
        contenedor_tipos.setLayout(self.fila_tipos)
        self.cmb_periodo = QComboBox()
        for p in prefs.PERIODOS:
            self.cmb_periodo.addItem(t(prefs.NOMBRE_PERIODO[p]), p)
        self.fecha_desde = QDateEdit(QDate.currentDate().addDays(-7))
        self.fecha_hasta = QDateEdit(QDate.currentDate())
        for f in (self.fecha_desde, self.fecha_hasta):
            f.setCalendarPopup(True)
            f.setDisplayFormat("dd/MM/yyyy")
        self.fila_fechas = QWidget()
        lf = QHBoxLayout(self.fila_fechas)
        lf.setContentsMargins(0, 0, 0, 0)
        lf.addWidget(QLabel(t("Desde")))
        lf.addWidget(self.fecha_desde)
        lf.addWidget(QLabel(t("Hasta")))
        lf.addWidget(self.fecha_hasta)
        self.cmb_agrupar = QComboBox()
        for g in prefs.AGRUPACIONES:
            self.cmb_agrupar.addItem(t(prefs.NOMBRE_AGRUPACION[g]), g)
        self.cmb_orden = QComboBox()
        for o in prefs.ORDENES:
            self.cmb_orden.addItem(t(prefs.NOMBRE_ORDEN[o]), o)
        self.spin_top = QSpinBox()
        self.spin_top.setRange(0, 50)
        self.spin_top.setSpecialValueText(t("Todos los elementos"))
        self.chk_leyenda = QCheckBox(t("Mostrar leyenda"))
        self.chk_etiquetas = QCheckBox(t("Mostrar valores"))
        self.cmb_tam = QComboBox()
        for tam in prefs.TAMANOS:
            self.cmb_tam.addItem(t(prefs.NOMBRE_TAMANO[tam]), tam)
        filas = [(t("Nombre del gráfico"), self.txt_titulo), (t("Fuente de datos"), self.cmb_fuente),
                 (t("Visualización"), contenedor_tipos), (t("Período"), self.cmb_periodo), ("", self.fila_fechas),
                 (t("Agrupación"), self.cmb_agrupar), (t("Orden"), self.cmb_orden),
                 (t("Elementos mostrados"), self.spin_top), ("", self.chk_leyenda), ("", self.chk_etiquetas),
                 (t("Tamaño"), self.cmb_tam)]
        self._filas: dict[str, tuple[QWidget, QWidget]] = {}
        for etiqueta, campo in filas:
            rotulo = QLabel(etiqueta)
            rotulo.setObjectName("ayuda")
            forma.addRow(rotulo, campo)
            self._filas[etiqueta or str(id(campo))] = (rotulo, campo)
        self._rotulos = {id(campo): rotulo for _k, (rotulo, campo) in self._filas.items()}
        izq = QWidget()
        izq.setObjectName("hojaPanel")
        izq.setLayout(forma)
        izq.setFixedWidth(430)
        derecha = QVBoxLayout()
        sub = QLabel(t("Vista previa"))
        sub.setObjectName("ayuda")
        self.previa = GraficoPersonal()
        self.previa.setMinimumHeight(260)
        marco = QFrame()
        marco.setObjectName("card")
        lm = QVBoxLayout(marco)
        lm.setContentsMargins(12, 12, 12, 12)
        lm.addWidget(self.previa)
        derecha.addWidget(sub)
        derecha.addWidget(marco, 1)
        cuerpo.addWidget(izq)
        cuerpo.addLayout(derecha, 1)
        self.cuerpo.addLayout(cuerpo, 1)
        self.btn_listo = QPushButton(t("Listo"))
        self.btn_listo.setObjectName("primario")
        self.btn_listo.clicked.connect(self.cerrar)
        pie = QHBoxLayout()
        pie.addStretch(1)
        pie.addWidget(self.btn_listo)
        self.cuerpo.addLayout(pie)
        for w in (self.cmb_fuente, self.cmb_periodo, self.cmb_agrupar, self.cmb_orden, self.cmb_tam):
            w.currentIndexChanged.connect(lambda _i, ww=w: self._cambio(ww))
        self.txt_titulo.textEdited.connect(lambda _t: self._cambio(None))
        self.spin_top.valueChanged.connect(lambda _v: self._cambio(None))
        self.chk_leyenda.toggled.connect(lambda _v: self._cambio(None))
        self.chk_etiquetas.toggled.connect(lambda _v: self._cambio(None))
        self.fecha_desde.dateChanged.connect(lambda _d: self._cambio(None))
        self.fecha_hasta.dateChanged.connect(lambda _d: self._cambio(None))
        self._tipo = ""

    # ------------------------------------------------------------------ carga
    def abrir_con(self, item: prefs.Item) -> None:
        self._id = item.id
        self._cargando = True
        d = item.definicion
        o = item.opciones
        self.cmb_fuente.setCurrentIndex(self.cmb_fuente.findData(item.clave))
        self.txt_titulo.setText(o.get("titulo", ""))
        self.txt_titulo.setPlaceholderText(t(d.nombre))
        self._tipo = o.get("tipo", d.tipo_defecto)
        self.cmb_periodo.setCurrentIndex(max(0, self.cmb_periodo.findData(o.get("periodo", "todo"))))
        for campo, ed in (("desde", self.fecha_desde), ("hasta", self.fecha_hasta)):
            f = QDate.fromString(o.get(campo, ""), Qt.DateFormat.ISODate)
            if f.isValid():
                ed.setDate(f)
        self.cmb_agrupar.setCurrentIndex(max(0, self.cmb_agrupar.findData(o.get("agrupar", "auto"))))
        self.cmb_orden.setCurrentIndex(max(0, self.cmb_orden.findData(o.get("orden", "original"))))
        self.spin_top.setValue(int(o.get("top", 0) or 0))
        self.chk_leyenda.setChecked(bool(o.get("leyenda", True)))
        self.chk_etiquetas.setChecked(bool(o.get("etiquetas", True)))
        self.cmb_tam.setCurrentIndex(max(0, self.cmb_tam.findData(item.tam)))
        self._cargando = False
        self._reconstruir_tipos()
        self._visibilidad()
        self._refrescar_previa()
        self.abrir()

    def _definicion(self) -> prefs.Def:
        return prefs.POR_CLAVE[self.cmb_fuente.currentData()]

    def _reconstruir_tipos(self) -> None:
        d = self._definicion()
        while self.fila_tipos.count():
            w = self.fila_tipos.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self._tipos = {}
        if self._tipo not in d.tipos:
            self._tipo = d.tipo_defecto
        for i, tp in enumerate(d.tipos):
            b = QToolButton()
            b.setObjectName("tipoGrafico")
            b.setCheckable(True)
            b.setChecked(tp == self._tipo)
            b.setToolTip(t(prefs.NOMBRE_TIPO[tp]))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            lay = QVBoxLayout(b)
            lay.setContentsMargins(2, 2, 2, 2)
            pic = Pictograma(tp, 62, 40)
            pic.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lay.addWidget(pic)
            b.setFixedSize(70, 48)
            b.clicked.connect(lambda _c=False, x=tp: self._elegir_tipo(x))
            self._tipos[tp] = b
            self.fila_tipos.addWidget(b, i // 5, i % 5)

    def _elegir_tipo(self, tp: str) -> None:
        self._tipo = tp
        for k, b in self._tipos.items():
            b.setChecked(k == tp)
        self._cambio(None)

    def _visibilidad(self) -> None:
        d = self._definicion()
        temporal = d.temporal
        categorica = d.clave in CATEGORICAS
        self._mostrar(self.cmb_periodo, temporal)
        self._mostrar(self.fila_fechas, temporal and self.cmb_periodo.currentData() == "personalizado")
        self._mostrar(self.cmb_agrupar, temporal and d.clave in ("lecturas_tiempo", "operador_tiempo"))
        self._mostrar(self.cmb_orden, categorica)
        self._mostrar(self.spin_top, categorica or d.clave == "operador_tiempo")
        self._mostrar(self.chk_leyenda, True)
        self._mostrar(self.chk_etiquetas, self._tipo not in ("lineas", "area", "evolucion"))

    def _mostrar(self, campo: QWidget, si: bool) -> None:
        campo.setVisible(si)
        rotulo = self._rotulos.get(id(campo))
        if rotulo is not None:
            rotulo.setVisible(si)

    # ------------------------------------------------------------------ cambios
    def opciones(self) -> dict:
        return {"titulo": self.txt_titulo.text().strip(), "tipo": self._tipo,
                "periodo": self.cmb_periodo.currentData(),
                "desde": self.fecha_desde.date().toString(Qt.DateFormat.ISODate),
                "hasta": self.fecha_hasta.date().toString(Qt.DateFormat.ISODate),
                "agrupar": self.cmb_agrupar.currentData(), "orden": self.cmb_orden.currentData(),
                "top": self.spin_top.value(), "leyenda": self.chk_leyenda.isChecked(),
                "etiquetas": self.chk_etiquetas.isChecked()}

    def _cambio(self, origen) -> None:
        if self._cargando:
            return
        if origen is self.cmb_fuente:
            self.txt_titulo.setPlaceholderText(t(self._definicion().nombre))
            self._reconstruir_tipos()
        self._visibilidad()
        self._refrescar_previa()
        self.cambiado.emit(self._id, self.cmb_fuente.currentData(), self.opciones(), self.cmb_tam.currentData())

    def _refrescar_previa(self) -> None:
        d = self._definicion()
        o = self.opciones()
        self.previa.poner(self._proveedor(d.clave, o), self._tipo, o["leyenda"], o["etiquetas"], False, animar=False)
