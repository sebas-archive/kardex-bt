"""Command palette (Ctrl+K) y overlay de atajos (?).

La paleta es el índice de todo lo que se puede hacer: pantallas, acciones de la vista activa y atajos. Los resultados
se filtran en vivo, se resaltan las coincidencias y se navegan con ↑/↓ + Enter. Las búsquedas recientes se recuerdan
en ``QSettings``.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Callable

from PyQt6.QtCore import QEvent, QPointF, QSettings, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from . import motion, widgets

VERDE = "#10B981"


def _plano(texto: str) -> str:
    """Minúsculas sin acentos, conservando la longitud (para resaltar sin desalinear)."""
    return "".join(c if not unicodedata.combining(c) else "" for c in unicodedata.normalize("NFD", texto.lower()))


@dataclass
class Atajo:
    id: str
    titulo: str
    categoria: str
    secuencia: str
    fn: Callable[[], None]
    detalle: str = ""
    habilitado: Callable[[], bool] | None = None


class RegistroAtajos:
    """Una sola lista de acciones para la paleta, la ayuda y los QShortcut."""

    def __init__(self) -> None:
        self._items: dict[str, Atajo] = {}
        self._ajustes = QSettings("GestionInventario", "Interfaz")

    def registrar(self, atajo: Atajo) -> Atajo:
        self._items[atajo.id] = atajo
        return atajo

    def quitar(self, id_: str) -> None:
        self._items.pop(id_, None)

    def entradas(self) -> list[Atajo]:
        return [a for a in self._items.values() if a.habilitado is None or a.habilitado()]

    def por_id(self, id_: str) -> Atajo | None:
        return self._items.get(id_)

    def recientes(self) -> list[str]:
        valor = self._ajustes.value("paleta/recientes", [])
        if isinstance(valor, str):
            return [v for v in valor.split("|") if v]
        return list(valor or [])

    def recordar(self, id_: str) -> None:
        recientes = [r for r in self.recientes() if r != id_]
        recientes.insert(0, id_)
        self._ajustes.setValue("paleta/recientes", "|".join(recientes[:6]))


class _DelegatePaleta(QStyledItemDelegate):
    """Dibuja cada resultado: título resaltado, categoría, atajo y selección con gradiente."""

    def __init__(self, lista: QListWidget) -> None:
        super().__init__(lista)
        self._consulta = ""

    def set_consulta(self, texto: str) -> None:
        self._consulta = _plano(texto)

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), 56)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = option.rect.adjusted(6, 3, -6, -3)
        from PyQt6.QtWidgets import QStyle

        seleccionado = bool(option.state & QStyle.StateFlag.State_Selected)
        if seleccionado:
            gradiente = QLinearGradient(QPointF(r.left(), r.top()), QPointF(r.right(), r.top()))
            gradiente.setColorAt(0.0, QColor("#12352A"))
            gradiente.setColorAt(1.0, QColor("#0E1F19"))
            painter.setBrush(gradiente)
            painter.setPen(QPen(QColor(VERDE), 1))
            painter.drawRoundedRect(r, 9, 9)
        titulo = index.data(Qt.ItemDataRole.UserRole) or ""
        categoria = index.data(Qt.ItemDataRole.UserRole + 1) or ""
        secuencia = index.data(Qt.ItemDataRole.UserRole + 2) or ""
        detalle = index.data(Qt.ItemDataRole.UserRole + 3) or ""

        fuente = QFont(option.font)
        fuente.setPixelSize(14)
        fuente.setBold(True)
        painter.setFont(fuente)
        fm = QFontMetrics(fuente)
        x, y = r.left() + 12, r.top() + 22
        # Resaltado de la coincidencia (fondo amarillo sutil detrás del texto).
        posicion = _plano(titulo).find(self._consulta) if self._consulta else -1
        if posicion >= 0 and self._consulta:
            prefijo = fm.horizontalAdvance(titulo[:posicion])
            ancho = fm.horizontalAdvance(titulo[posicion:posicion + len(self._consulta)])
            resalte = QColor("#F5C542")
            resalte.setAlpha(60)
            painter.fillRect(r.left() + 12 + prefijo, r.top() + 8, max(2, ancho), 20, resalte)
        painter.setPen(QColor("#FFFFFF" if seleccionado else "#EDEDED"))
        painter.drawText(x, y, titulo)

        fuente.setPixelSize(11)
        fuente.setBold(False)
        painter.setFont(fuente)
        painter.setPen(QColor("#8A8A8A"))
        subtitulo = categoria + (f" · {detalle}" if detalle else "")
        painter.drawText(r.left() + 12, r.top() + 40, subtitulo)

        if secuencia:
            chip = QFont(option.font)
            chip.setPixelSize(10)
            chip.setBold(True)
            painter.setFont(chip)
            fmc = QFontMetrics(chip)
            ancho = fmc.horizontalAdvance(secuencia) + 14
            caja = r.adjusted(r.width() - ancho - 10, 12, -10, -12)
            painter.setPen(QPen(QColor("#3A3A3A"), 1))
            painter.setBrush(QColor("#1C1C1C"))
            painter.drawRoundedRect(caja, 5, 5)
            painter.setPen(QColor("#A3A3A3"))
            painter.drawText(caja, Qt.AlignmentFlag.AlignCenter, secuencia)
        painter.restore()


class PaletaComandos(QWidget):
    """Spotlight de la app: se abre con Ctrl+K, filtra en vivo y ejecuta con Enter.

    Es un hijo de la ventana (no un diálogo aparte): el backdrop difuminado y la caja quedan dentro del mismo
    lienzo, así se pueden capturar juntos y la navegación por teclado sigue siendo de la ventana.
    """

    elegido = pyqtSignal(str)

    def __init__(self, host: QWidget, registro: RegistroAtajos,
                 extras: Callable[[str], list[Atajo]] | None = None) -> None:
        super().__init__(host)
        self._host = host
        self._registro = registro
        self._extras = extras
        self.setObjectName("paleta")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        self._fondo = QLabel(self)
        self._fondo.setScaledContents(True)
        self._fondo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._velo = QFrame(self)
        self._velo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._velo.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._velo.setStyleSheet("background: rgba(0, 0, 0, 0.60);")

        self._caja = QFrame(self)
        self._caja.setObjectName("paletaCaja")
        self._caja.setMinimumHeight(440)
        en_caja = QVBoxLayout(self._caja)
        en_caja.setContentsMargins(16, 14, 16, 12)
        en_caja.setSpacing(10)
        cabecera = QHBoxLayout()
        lupa = QLabel("⌕")
        lupa.setObjectName("paletaLupa")
        self.campo = QLineEdit()
        self.campo.setObjectName("paletaCampo")
        self.campo.setPlaceholderText("Buscar pantallas, acciones o atajos…")
        self.campo.setClearButtonEnabled(True)
        self.campo.textChanged.connect(self._filtrar)
        self.campo.returnPressed.connect(self._elegir_actual)
        cabecera.addWidget(lupa)
        cabecera.addWidget(self.campo, 1)
        en_caja.addLayout(cabecera)
        self.lista = QListWidget()
        self.lista.setObjectName("paletaLista")
        self.lista.setItemDelegate(_DelegatePaleta(self.lista))
        self.lista.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lista.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.lista.setMinimumHeight(330)
        self.lista.itemActivated.connect(lambda _: self._elegir_actual())
        en_caja.addWidget(self.lista, 1)
        pie = QHBoxLayout()
        for tecla, texto in (("↑↓", "navegar"), ("Enter", "abrir"), ("Esc", "cerrar")):
            ayuda = QLabel(f"{tecla}  {texto}")
            ayuda.setObjectName("paletaPie")
            pie.addWidget(ayuda)
        pie.addStretch(1)
        self.lbl_total = QLabel("")
        self.lbl_total.setObjectName("paletaPie")
        pie.addWidget(self.lbl_total)
        en_caja.addLayout(pie)

        self.campo.installEventFilter(self)
        self._anim: object | None = None
        self._lista_filtrada: list[Atajo] = []
        self.hide()

    # ------------------------------------------------------------------ abrir / cerrar
    def abrir(self, texto: str = "") -> None:
        self.setGeometry(self._host.rect())
        self._fondo.setGeometry(self.rect())
        self._velo.setGeometry(self.rect())
        mapa = self._host.grab()
        self._fondo.setPixmap(mapa)
        desenfoque = QGraphicsBlurEffect(self._fondo)
        desenfoque.setBlurRadius(12)
        self._fondo.setGraphicsEffect(desenfoque)
        self._caja.setFixedWidth(min(660, max(420, self.width() - 120)))
        self._reubicar()
        self.campo.setText(texto)
        self.campo.selectAll()
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.campo.setFocus(Qt.FocusReason.ShortcutFocusReason)
        motion.desvanecer(self._caja, 0.0, 1.0, motion.NORMAL)
        al_terminar = QTimer(self)
        al_terminar.setSingleShot(True)
        al_terminar.timeout.connect(lambda: self.campo.setFocus(Qt.FocusReason.ShortcutFocusReason))
        al_terminar.start(30)
        self._filtrar(texto)

    def cerrar(self) -> None:
        self.hide()
        self._host.setFocus(Qt.FocusReason.OtherFocusReason)

    def _reubicar(self) -> None:
        self._caja.adjustSize()
        self._caja.move((self.width() - self._caja.width()) // 2, max(40, int(self.height() * 0.14)))

    # ------------------------------------------------------------------ búsqueda
    def _candidatos(self, texto: str) -> list[Atajo]:
        entradas = list(self._registro.entradas())
        if self._extras is not None:
            entradas.extend(self._extras(texto))
        consulta = _plano(texto.strip())
        if not consulta:
            recientes = self._registro.recientes()
            orden = {id_: i for i, id_ in enumerate(recientes)}
            return sorted(entradas, key=lambda a: (orden.get(a.id, 99), a.categoria, a.titulo))
        encontrados = []
        for atajo in entradas:
            campos = _plano(" ".join((atajo.titulo, atajo.categoria, atajo.detalle, atajo.secuencia)))
            if consulta in campos:
                empieza = _plano(atajo.titulo).startswith(consulta)
                encontrados.append((0 if empieza else 1, len(atajo.titulo), atajo))
        encontrados.sort(key=lambda t: (t[0], t[1]))
        return [a for _p, _l, a in encontrados]

    def _filtrar(self, texto: str) -> None:
        atajos = self._candidatos(texto)
        self._lista_filtrada = atajos
        self.lista.clear()
        delegate = self.lista.itemDelegate()
        delegate.set_consulta(texto.strip())
        recientes = set(self._registro.recientes()) if not texto.strip() else set()
        for atajo in atajos:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, atajo.titulo)
            item.setData(Qt.ItemDataRole.UserRole + 1, "Reciente" if atajo.id in recientes else atajo.categoria)
            item.setData(Qt.ItemDataRole.UserRole + 2, atajo.secuencia)
            item.setData(Qt.ItemDataRole.UserRole + 3, atajo.detalle)
            item.setData(Qt.ItemDataRole.UserRole + 4, atajo.id)
            item.setSizeHint(QSize(0, 56))
            self.lista.addItem(item)
        if atajos:
            self.lista.setCurrentRow(0)
        self.lbl_total.setText(f"{len(atajos)} resultado{'s' if len(atajos) != 1 else ''}" if atajos else "Sin resultados")
        self._caja.adjustSize()
        self._reubicar()
        motion.detener(self._anim)  # type: ignore[arg-type]
        self._anim = motion.desvanecer(self.lista, 0.35, 1.0, motion.RAPIDO)

    def _elegir_actual(self) -> None:
        item = self.lista.currentItem()
        if item is None:
            return
        id_ = item.data(Qt.ItemDataRole.UserRole + 4)
        atajo = self._registro.por_id(id_)
        if atajo is None:
            for extra in self._extras("") if self._extras else []:
                if extra.id == id_:
                    atajo = extra
                    break
        if atajo is None:
            return
        self._registro.recordar(id_)
        self.cerrar()
        self.elegido.emit(id_)
        QTimer.singleShot(0, atajo.fn)

    # ------------------------------------------------------------------ eventos
    def eventFilter(self, objeto, evento) -> bool:
        if objeto is self.campo and evento.type() == QEvent.Type.KeyPress:
            if evento.key() == Qt.Key.Key_Down:
                self.lista.setCurrentRow(min(self.lista.currentRow() + 1, self.lista.count() - 1))
                return True
            if evento.key() == Qt.Key.Key_Up:
                self.lista.setCurrentRow(max(self.lista.currentRow() - 1, 0))
                return True
        return super().eventFilter(objeto, evento)

    def mousePressEvent(self, evento) -> None:
        if not self._caja.geometry().contains(evento.position().toPoint()):
            self.cerrar()
            evento.accept()
            return
        super().mousePressEvent(evento)

    def keyPressEvent(self, evento) -> None:
        if evento.key() == Qt.Key.Key_Escape:
            self.cerrar()
            return
        if evento.key() == Qt.Key.Key_Down:
            self.lista.setCurrentRow(min(self.lista.currentRow() + 1, self.lista.count() - 1))
            return
        if evento.key() == Qt.Key.Key_Up:
            self.lista.setCurrentRow(max(self.lista.currentRow() - 1, 0))
            return
        super().keyPressEvent(evento)

    def resizeEvent(self, evento) -> None:
        self._fondo.setGeometry(self.rect())
        self._velo.setGeometry(self.rect())
        self._reubicar()
        super().resizeEvent(evento)


class AyudaAtajos(QDialog):
    """Overlay con todos los atajos disponibles, agrupados."""

    def __init__(self, host: QWidget, registro: RegistroAtajos) -> None:
        super().__init__(host.window())
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setGeometry(host.window().geometry())
        fondo = QFrame(self)
        fondo.setStyleSheet("background: rgba(0, 0, 0, 0.66);")
        fondo.setGeometry(self.rect())
        caja = QFrame(self)
        caja.setObjectName("ayudaCaja")
        caja.setFixedWidth(min(720, self.width() - 100))
        en_caja = QVBoxLayout(caja)
        en_caja.setContentsMargins(26, 22, 26, 20)
        en_caja.setSpacing(12)
        titulo = QLabel("Atajos y gestos")
        titulo.setObjectName("modalTitulo")
        en_caja.addWidget(titulo)
        intro = QLabel("Todo se puede hacer sin mouse. Los atajos de la vista activa aparecen también en Ctrl+K.")
        intro.setObjectName("ayuda")
        intro.setWordWrap(True)
        en_caja.addWidget(intro)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        cuerpo = QWidget()
        por_categoria: dict[str, list[Atajo]] = {}
        for atajo in registro.entradas():
            por_categoria.setdefault(atajo.categoria, []).append(atajo)
        rejilla = QVBoxLayout(cuerpo)
        rejilla.setSpacing(12)
        for categoria, atajos in por_categoria.items():
            rotulo = QLabel(categoria.upper())
            rotulo.setObjectName("ayudaCategoria")
            rejilla.addWidget(rotulo)
            for atajo in sorted(atajos, key=lambda a: a.titulo):
                fila = QHBoxLayout()
                nombre = QLabel(atajo.titulo)
                nombre.setObjectName("ayudaAtajo")
                tecla = QLabel(atajo.secuencia or "—")
                tecla.setObjectName("ayudaTecla")
                tecla.setAlignment(Qt.AlignmentFlag.AlignCenter)
                fila.addWidget(nombre, 1)
                fila.addWidget(tecla)
                rejilla.addLayout(fila)
        rejilla.addStretch(1)
        area.setWidget(cuerpo)
        en_caja.addWidget(area, 1)
        cerrar = QLabel("Esc para cerrar")
        cerrar.setObjectName("paletaPie")
        en_caja.addWidget(cerrar)
        caja.adjustSize()
        caja.move((self.width() - caja.width()) // 2, max(30, (self.height() - caja.height()) // 2))

    def keyPressEvent(self, evento) -> None:
        if evento.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(evento)
