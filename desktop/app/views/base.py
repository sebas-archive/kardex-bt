"""Piezas comunes de las vistas: contrato, ejecución de consultas fuera de la UI y avisos de estado."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable, Protocol

from PyQt6 import sip
from PyQt6.QtCore import QObject, QPointF, Qt, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from ..i18n import t
from ..workers import QueryWorker
from .isla import isla
from .motion_global import BarridoCarga

ESTILO = """
QMainWindow, QWidget { background: #0A0A0A; color: #EDEDED; font-size: 13px; }
QWidget#marco { background: #161616; }
QWidget#contenido { background: transparent; }
QToolTip { background: #262626; color: #EDEDED; border: 1px solid #333333; padding: 6px 8px; }

/* Barra lateral: sin fondo propio, se funde con el marco exterior (#161616) */
QFrame#lateral, QFrame#lateral QWidget { background: transparent; border: none; }
QFrame#lateral QLabel { background: transparent; }
QLabel#marca { font-size: 16px; font-weight: 700; color: #FFFFFF; }
QPushButton#nav { text-align: left; padding: 10px 12px; border: none; border-radius: 8px; background: transparent;
                  color: #A3A3A3; font-weight: 600; }
QPushButton#nav:hover { background: rgba(255,255,255,0.06); color: #FFFFFF; }
QPushButton#nav:checked { background: rgba(255,255,255,0.10); color: #FFFFFF; }
QPushButton#nav:focus { border: 1px solid #5B5B5B; }
QFrame#lateral[contraida="true"] QPushButton#nav { text-align: center; padding: 10px 0; }
QPushButton#iconoLateral { border: none; border-radius: 8px; background: transparent; min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px; padding: 0; }
QPushButton#iconoLateral:hover { background: rgba(255,255,255,0.08); }
QPushButton#iconoLateral:focus { border: 1px solid #5B5B5B; }
QFrame#pieCuenta { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; }
QFrame#pieCuenta[contraida="true"] { border: none; background: transparent; }
QFrame#pieCuenta QLabel, QFrame#pieCuenta QWidget { background: transparent; }
QPushButton#cuenta { border: none; background: transparent; text-align: left; border-radius: 8px; }
QPushButton#cuenta:hover { background: rgba(255,255,255,0.06); }
QFrame#pieCuenta QLabel#avatar { background: #10B981; color: #04130E; border-radius: 18px; font-weight: 700; font-size: 14px; }
QLabel#usuarioNombre { font-weight: 600; font-size: 12px; color: #FFFFFF; }
QLabel#usuarioRol { color: #8A8A8A; font-size: 11px; }

/* Lienzo principal encajado en el marco */
QFrame#lienzo { background: #0A0A0A; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; }

/* Encabezado de cada página */
QLabel#tituloPagina { font-size: 22px; font-weight: 600; background: transparent; }
QLabel#chipEstado { background: #1C1C1C; color: #A3A3A3; border-radius: 12px; padding: 0px 12px; font-size: 12px; }
QLabel#chipEstado[estado="ok"] { background: #10261F; color: #34D399; }
QLabel#chipEstado[estado="activo"] { background: #1F2350; color: #A5B4FC; }
QLabel#chipEstado[estado="error"] { background: #3A1512; color: #F87171; }

/* Tarjetas */
QFrame#card { background: #111111; border: 1px solid #232323; border-radius: 12px; }
QFrame#card QLabel { background: transparent; }
QLabel#cardTitulo { color: #8A8A8A; font-size: 12px; }
QLabel#cardValor { font-size: 26px; font-weight: 600; }
QLabel#cardDetalle { color: #8A8A8A; font-size: 11px; }
QLabel#seccion { font-size: 14px; font-weight: 600; background: transparent; }
QLabel#subtitulo, QLabel#ayuda { color: #8A8A8A; background: transparent; }
QLabel#insignia { border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600; color: #A3A3A3; background: #1C1C1C; }
QLabel#insignia[estado="ABIERTO"], QLabel#insignia[estado="ADMIN"], QLabel#insignia[estado="ACTIVO"] { background: #10261F; color: #34D399; }
QLabel#insignia[estado="CERRADO"] { background: #1C1C1C; color: #A3A3A3; }
QLabel#insignia[estado="INVENTARIO"], QLabel#insignia[estado="OPERADOR"] { background: #1F2350; color: #A5B4FC; }
QLabel#insignia[estado="SUSPENDIDO"], QLabel#insignia[estado="RECHAZADO"] { background: #3A1512; color: #F87171; }
QLabel#insignia[estado="PENDIENTE"] { background: #2B2410; color: #FBBF24; }
QLabel#avatarGrande { background: transparent; border: none; }
QLabel#resumen { color: #A3A3A3; background: transparent; }
QLabel#estadoSync { font-size: 19px; font-weight: 600; background: transparent; }
QLabel#codigoSync { font-size: 54px; font-weight: 700; font-family: "DejaVu Sans Mono"; color: #34D399; background: transparent; }
QLabel#errorFormulario { color: #F87171; background: transparent; }
QLabel#avisoFormulario { color: #34D399; background: transparent; }

/* Acceso */
QFrame#panelMarca { background: #0F2A24; border: none; }
QFrame#panelMarca QLabel { color: #FFFFFF; background: transparent; }
QLabel#tituloAcceso { font-size: 22px; font-weight: 600; background: transparent; }
QFrame#card QStackedWidget, QWidget#formulario { background: #111111; }
QPushButton#verAviso { border: 1px solid #10B981; border-radius: 6px; background: transparent; color: #34D399;
                       font-weight: 700; font-size: 12px; padding: 2px 12px; }
QPushButton#verAviso:hover { background: #10B981; color: #04130E; }
QPushButton#enlace { border: none; background: transparent; color: #34D399; font-weight: 600; padding: 4px; }
QPushButton#enlace:hover { color: #6EE7B7; background: transparent; }

/* Avisos de estado */
QFrame#aviso { background: #2B2410; border: 1px solid #5C4A16; border-radius: 10px; }
QFrame#aviso[error="true"] { background: #3A1512; border: 1px solid #7A2A24; }
QFrame#aviso QLabel { background: transparent; }

/* Botones */
QPushButton { padding: 7px 16px; border: 1px solid #2E2E2E; border-radius: 8px; background: #111111; font-weight: 600; }
QPushButton:hover { background: #1C1C1C; }
QPushButton:pressed { background: #232323; }
QPushButton:disabled { color: #6E6E6E; background: #1C1C1C; border-color: #232323; }
QPushButton#primario { background: #10B981; color: #04130E; border: none; padding: 9px 20px; }
QPushButton#primario:hover { background: #34D399; }
QPushButton#primario:disabled { background: #1E3A32; color: #6E6E6E; }
QPushButton#peligro { color: #F87171; border-color: #7A2A24; }
QPushButton#peligro:hover { background: #3A1512; }
QPushButton#chip { border-radius: 14px; padding: 5px 14px; background: #111111; border: 1px solid #2E2E2E; font-weight: 600; }
QPushButton#chip:hover { background: #1C1C1C; }
QPushButton#chip:checked { background: #10B981; color: #04130E; border-color: #10B981; }

/* Tablas y campos */
QTableView, QTableWidget { background: #111111; border: 1px solid #232323; border-radius: 10px; gridline-color: #1C1C1C;
                           selection-background-color: #10261F; selection-color: #FFFFFF; }
QHeaderView::section { background: #0F0F0F; padding: 8px 6px; border: none; border-bottom: 1px solid #232323;
                       font-weight: 600; color: #A3A3A3; }
QLineEdit, QComboBox, QSpinBox { padding: 7px 10px; border: 1px solid #2E2E2E; border-radius: 8px; background: #111111; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 2px solid #10B981; padding: 6px 9px; }
QLineEdit[valido="true"] { border: 1px solid #10B981; }
QLineEdit[invalido="true"] { border: 1px solid #F87171; }
QLineEdit[invalido="true"]:focus { border: 2px solid #F87171; padding: 6px 9px; }
QLineEdit[valido="true"]:focus { border: 2px solid #10B981; padding: 6px 9px; }
QComboBox::drop-down, QSpinBox::up-button, QSpinBox::down-button { border: none; width: 22px; background: transparent; }
QComboBox QAbstractItemView { background: #111111; border: 1px solid #2E2E2E; selection-background-color: #10261F;
                              selection-color: #EDEDED; outline: none; }
QProgressBar { border: none; background: #232323; border-radius: 4px; height: 8px; }
QProgressBar::chunk { background: #10B981; border-radius: 4px; }
QScrollArea { border: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #2E2E2E; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ---------------------------------------------------------------- interactividad */
QPushButton:hover { background: #1C1C1C; border-color: #3A3A3A; }
QPushButton:pressed { background: #262626; }
QPushButton:focus { border: 1px solid #10B981; }
QToolButton { border: none; background: transparent; color: #A3A3A3; border-radius: 6px; padding: 2px; }
QToolButton:hover { background: rgba(255,255,255,0.08); color: #FFFFFF; }
QToolButton:focus { border: 1px solid #10B981; }

/* Barra lateral: ítem activo con indicador y glow del color primario (sin cambiar la identidad) */
QPushButton#nav { padding-left: 12px; border-left: 3px solid transparent; }
QPushButton#nav:hover { background: rgba(255,255,255,0.07); color: #FFFFFF; }
QPushButton#nav:checked { border-left: 3px solid transparent; background: rgba(255,255,255,0.10); color: #FFFFFF; }
QPushButton#nav:checked:hover { background: rgba(255,255,255,0.13); }
QFrame#lateral[contraida="true"] QPushButton#nav { text-align: center; padding-left: 0; border-left: 3px solid transparent; }
QFrame#lateral[contraida="true"] QPushButton#nav:checked { border-left: 3px solid transparent; }
QFrame#separadorNav { background: rgba(255,255,255,0.07); max-height: 1px; margin: 6px 10px; }

/* Tarjetas con hover rico */
QFrame#card { border: 1px solid #232323; }
QFrame#card[hover="true"] { border: 1px solid #2F6B57; }
QWidget#accionesCard { background: transparent; }
QPushButton#accionCard { padding: 5px 10px; font-size: 11px; border-radius: 7px; color: #CFCFCF; }
QPushButton#accionCard[primaria="true"] { background: #10B981; color: #04130E; border: none; }
QLabel#cardPista { color: #34D399; font-size: 11px; font-weight: 600; background: transparent; }

/* Drawer */
QLabel#drawerFondo { background: #0A0A0A; }
QFrame#drawerVelo { background: rgba(0,0,0,0.55); }
QFrame#drawerPanel { background: #0F0F0F; border-left: 1px solid #2A2A2A; }
QLabel#drawerTitulo { font-size: 18px; font-weight: 600; color: #FFFFFF; background: transparent; }
QToolButton#cerrarDrawer { color: #A3A3A3; font-size: 15px; min-width: 28px; min-height: 28px; }
QToolButton#cerrarDrawer:hover { background: #2A2A2A; color: #FFFFFF; }
QLabel#datoDrawer { color: #EDEDED; font-weight: 600; background: transparent; }

/* Modal de confirmación */
QFrame#modalCaja { background: #121212; border: 1px solid #333333; border-radius: 16px; }
QLabel#modalTitulo { font-size: 18px; font-weight: 600; color: #FFFFFF; background: transparent; }
QLabel#modalTexto { color: #CFCFCF; font-size: 13px; background: transparent; }
QCheckBox { color: #CFCFCF; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #4A4A4A; background: #111111; }
QCheckBox::indicator:checked { background: #10B981; border-color: #10B981; }

/* Command palette */
QFrame#paletaCaja { background: #111111; border: 1px solid #343434; border-radius: 14px; }
QLineEdit#paletaCampo { font-size: 15px; padding: 10px 8px; border: none; background: transparent; }
QLineEdit#paletaCampo:focus { border: none; }
QLabel#paletaLupa { color: #10B981; font-size: 19px; padding-left: 4px; }
QListWidget#paletaLista { background: transparent; border: none; outline: none; }
QListWidget#paletaLista::item { border: none; }
QLabel#paletaPie { color: #6E6E6E; font-size: 11px; background: transparent; }
QToolButton#configAcceso { border: none; background: transparent; border-radius: 8px; padding: 4px; }
QToolButton#configAcceso:hover { background: rgba(255, 255, 255, 0.08); }
QToolButton#ayudaVista { color: #8A8A8A; font-size: 11px; font-weight: 700; min-width: 22px; max-width: 22px;
    min-height: 22px; max-height: 22px; border: 1px solid #3A3A3A; border-radius: 11px; }
QToolButton#ayudaVista:hover { color: #FFFFFF; border-color: #10B981; background: #133A2C; }

/* Ayuda de atajos */
QFrame#ayudaCaja { background: #111111; border: 1px solid #343434; border-radius: 14px; }
QLabel#ayudaCategoria { color: #10B981; font-size: 11px; font-weight: 700; letter-spacing: 1px; background: transparent; }
QLabel#ayudaAtajo { color: #EDEDED; font-size: 13px; background: transparent; }
QLabel#ayudaTecla { background: #1C1C1C; border: 1px solid #383838; border-radius: 6px; padding: 2px 8px;
    color: #CFCFCF; font-family: "DejaVu Sans Mono"; font-size: 11px; min-width: 42px; }

/* Chips de filtros activos */
QFrame#chipActivo { background: #132A22; border: 1px solid #2F6B57; border-radius: 13px; }
QLabel#chipActivoTexto { color: #6EE7B7; font-size: 11px; font-weight: 600; background: transparent; }
QToolButton#chipActivoCerrar { color: #6EE7B7; font-size: 10px; min-width: 16px; min-height: 16px; border-radius: 8px; }
QToolButton#chipActivoCerrar:hover { background: rgba(255,255,255,0.10); color: #FFFFFF; }

/* Barra de selección múltiple */
QFrame#barraLote { background: #1C1C1C; border: 1px solid #3A3A3A; border-radius: 12px; }
QLabel#barraLoteTexto { color: #FFFFFF; font-weight: 600; background: transparent; }
QPushButton#accionLote { padding: 5px 12px; font-size: 12px; }
QPushButton#accionLote[primaria="true"] { background: #10B981; color: #04130E; border: none; }

/* Acciones rápidas de fila */
QWidget#accionesFila { background: #1C1C1C; border: 1px solid #3A3A3A; border-radius: 7px; }
QToolButton#accionFila { color: #CFCFCF; font-size: 12px; }
QToolButton#accionFila:hover { background: #10B981; color: #04130E; }

/* Tooltip rico y tooltip de gráfica */
QWidget#tooltipRico { background: #1C1C1C; border: 1px solid #3A3A3A; border-radius: 9px; }
QLabel#tooltipTitulo { color: #FFFFFF; font-weight: 700; background: transparent; }
QLabel#tooltipTexto { color: #CFCFCF; font-size: 12px; background: transparent; }
QLabel#tooltipDato { color: #34D399; font-weight: 600; background: transparent; }
QLabel#tooltipGrafica { background: #1C1C1C; border: 1px solid #3A3A3A; border-radius: 7px; padding: 6px 9px;
    color: #EDEDED; font-size: 12px; }

/* Menú contextual */
QMenu#menuContexto { background: #1A1A1A; border: 1px solid #3A3A3A; border-radius: 9px; padding: 6px; }
QMenu#menuContexto::item { padding: 6px 18px; border-radius: 6px; color: #EDEDED; }
QMenu#menuContexto::item:selected { background: #133A2C; color: #FFFFFF; }
QMenu#menuContexto::separator { height: 1px; background: #2E2E2E; margin: 5px 8px; }

/* Tablas */
QTableView::item:hover, QTableWidget::item:hover { background: rgba(255,255,255,0.04); }
QHeaderView::section:hover { color: #EDEDED; background: #161616; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #2E2E2E; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* Encabezado que se compacta */
QLabel#tituloPagina[compacto="true"] { font-size: 17px; }

/* Acceso: tarjeta de dos paneles */
QFrame#tarjetaAcceso { background: #111111; border-radius: 18px; }
QWidget#panelFormulario { background: transparent; }
QLabel#tituloFormulario { font-size: 24px; font-weight: 700; background: transparent; }
QLabel#subtituloFormulario { color: #8A8A8A; background: transparent; }
QFrame#campoAcceso { background: #0F0F0F; border: 1px solid #2E2E2E; border-radius: 10px; }
QFrame#campoAcceso QLabel { background: transparent; }
QLineEdit#campoTexto { border: none; background: transparent; padding: 7px 0; font-size: 13px; }
QLineEdit#campoTexto:focus { border: none; }
QComboBox#campoCombo { background: #0F0F0F; border: 1px solid #2E2E2E; border-radius: 10px; padding: 8px 10px; }
QPushButton#botonPrincipal { background: #10B981; color: #04130E; border: none; border-radius: 10px;
                             padding: 11px 18px; font-weight: 700; }
QPushButton#botonPrincipal:hover { background: #34D399; }
QPushButton#botonPrincipal:disabled { background: #1E3A32; color: #8A8A8A; }
QPushButton#botonSecundario { background: transparent; color: #10B981; border: 1px solid #10B981;
                              border-radius: 10px; padding: 9px 16px; font-weight: 600; }
QPushButton#botonSecundario:hover { background: rgba(16, 185, 129, 0.12); }
QPushButton#enlaceAzul { border: none; background: transparent; color: #10B981; font-weight: 600; padding: 2px; }
QPushButton#enlaceAzul:hover { color: #34D399; }
QLabel#oAcceso { color: #8A8A8A; background: transparent; }
QFrame#separadorAcceso { background: #2E2E2E; max-height: 1px; }
QScrollArea#scrollAcceso { background: transparent; border: none; }
QWidget#paginaAcceso { background: transparent; }


/* ======================================================================================================
   Refinamiento visual. Tokens: radio 8 (controles) y 12 (tarjetas); alto de control ~34; espacios 4/8/12/16/24.
   Solo usa los colores ya definidos arriba; la barra lateral queda fuera (todo va acotado al lienzo o a popups). */
QToolTip { background: #1A1A1A; color: #EDEDED; border: 1px solid #333333; border-radius: 6px; padding: 5px 8px;
           font-size: 12px; }

/* Jerarquía tipográfica */
QLabel#tituloPagina { font-size: 22px; font-weight: 700; }
QLabel#seccion { font-size: 14px; font-weight: 600; }
QLabel#cardTitulo { color: #8A8A8A; font-size: 12px; font-weight: 500; }
QLabel#cardValor { font-size: 28px; font-weight: 600; }
QLabel#subtitulo, QLabel#ayuda { color: #8A8A8A; font-size: 12px; }
QLabel#estadoVistaTexto { color: #8A8A8A; font-size: 12px; background: transparent; padding: 18px 0; }
QFrame#estadoVista { background: transparent; border: none; }

/* Tarjetas */
QFrame#lienzo QFrame#card { background: #111111; border: 1px solid #232323; border-radius: 14px; }

/* Botones: un solo lenguaje (alto uniforme, hover, presionado, deshabilitado y foco) */
QFrame#lienzo QPushButton { min-height: 18px; padding: 7px 16px; border-radius: 9px; border: 1px solid #2E2E2E;
                            background: #111111; font-weight: 600; }
QFrame#lienzo QPushButton:hover { background: #1C1C1C; border-color: #3A3A3A; }
QFrame#lienzo QPushButton:pressed { background: #232323; }
QFrame#lienzo QPushButton:disabled { color: #6E6E6E; background: #161616; border-color: #232323; }
QFrame#lienzo QPushButton:focus { border: 1px solid #10B981; }
QFrame#lienzo QPushButton#primario { background: #10B981; color: #04130E; border: 1px solid #10B981; }
QFrame#lienzo QPushButton#primario:hover { background: #34D399; border-color: #34D399; }
QFrame#lienzo QPushButton#primario:pressed { background: #10B981; }
QFrame#lienzo QPushButton#primario:disabled { background: #1E3A32; color: #6E6E6E; border-color: #1E3A32; }
QFrame#lienzo QPushButton#peligro { color: #F87171; background: transparent; border: 1px solid #7A2A24; }
QFrame#lienzo QPushButton#peligro:hover { background: #3A1512; }
QFrame#lienzo QPushButton#peligro:disabled { color: #6E6E6E; border-color: #232323; background: transparent; }
QFrame#lienzo QPushButton#enlace { border: none; background: transparent; color: #34D399; padding: 4px 8px;
                                   min-height: 0; }
QFrame#lienzo QPushButton#enlace:hover { color: #6EE7B7; background: transparent; }

/* Campos: misma altura, borde suave y foco visible */
QFrame#lienzo QLineEdit, QFrame#lienzo QComboBox, QFrame#lienzo QSpinBox, QFrame#lienzo QDoubleSpinBox,
QFrame#lienzo QDateEdit { min-height: 18px; padding: 7px 12px; border: 1px solid #2E2E2E; border-radius: 9px;
                          background: #111111; selection-background-color: #10B981; selection-color: #04130E; }
QFrame#lienzo QLineEdit:hover, QFrame#lienzo QComboBox:hover, QFrame#lienzo QSpinBox:hover { border-color: #3A3A3A; }
QFrame#lienzo QLineEdit:focus, QFrame#lienzo QComboBox:focus, QFrame#lienzo QSpinBox:focus,
QFrame#lienzo QDateEdit:focus { border: 1px solid #10B981; padding: 7px 12px; }
QFrame#lienzo QLineEdit:disabled, QFrame#lienzo QComboBox:disabled, QFrame#lienzo QSpinBox:disabled {
    color: #6E6E6E; background: #161616; border-color: #232323; }
QFrame#lienzo QLineEdit[invalido="true"] { border: 1px solid #F87171; }
QFrame#lienzo QLineEdit[valido="true"] { border: 1px solid #10B981; }
QComboBox QAbstractItemView { background: #111111; border: 1px solid #2E2E2E; border-radius: 8px; padding: 4px;
                              selection-background-color: #10261F; selection-color: #EDEDED; outline: none; }
QCheckBox, QRadioButton { background: transparent; }
QRadioButton { color: #CFCFCF; spacing: 8px; }
QRadioButton::indicator { width: 16px; height: 16px; border-radius: 9px; border: 1px solid #4A4A4A; background: #111111; }
QRadioButton::indicator:checked { border: 5px solid #10B981; background: #111111; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: #10B981; }

/* Tablas: sin rejilla, filas con separador fino, encabezado discreto alineado a la izquierda */
QFrame#lienzo QTableView, QFrame#lienzo QTableWidget { background: #111111; border: 1px solid #232323; border-radius: 14px;
                                                       gridline-color: transparent; outline: none; }
QTableView::item, QTableWidget::item { padding: 0 10px; border: none; border-bottom: 1px solid #1C1C1C; }
QTableView::item:hover, QTableWidget::item:hover { background: rgba(255,255,255,0.035); }
QTableView::item:selected, QTableWidget::item:selected { background: #10261F; color: #FFFFFF; }
QHeaderView { background: transparent; qproperty-defaultAlignment: AlignLeft; }
QHeaderView::section { background: #0F0F0F; color: #8A8A8A; font-size: 11px; font-weight: 700; padding: 10px 10px;
                       border: none; border-bottom: 1px solid #232323; }
QTableView QLabel#insignia, QTableWidget QLabel#insignia { margin: 9px 12px; }
QTableView QComboBox, QTableWidget QComboBox { margin: 4px 8px; min-height: 16px; padding: 4px 10px; }
QTableCornerButton::section { background: #0F0F0F; border: none; }

/* Barras de desplazamiento finas */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #2E2E2E; border-radius: 4px; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #4A4A4A; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* Menús */
QMenu { background: #1A1A1A; border: 1px solid #333333; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 18px 7px 14px; border-radius: 6px; color: #EDEDED; margin: 1px 0; }
QMenu::item:selected { background: #133A2C; color: #FFFFFF; }
QMenu::item:disabled { color: #6E6E6E; }
QMenu::separator { height: 1px; background: #2E2E2E; margin: 5px 8px; }

/* Diálogos internos */
QDialog { background: #121212; }
QDialog QLabel { background: transparent; }
QDialogButtonBox QPushButton { min-width: 84px; }
QProgressBar { border: none; background: #232323; border-radius: 4px; max-height: 8px; text-align: center; }
QProgressBar::chunk { background: #10B981; border-radius: 4px; }

/* Personalización del dashboard */
QFrame#baldosa, QWidget#hojaPanel { background: transparent; border: none; }
QScrollArea#hojaScroll, QScrollArea#hojaScroll > QWidget > QWidget { background: transparent; }
QFrame#barraEdicion { background: #111111; border: 1px solid #232323; border-radius: 14px; }
QFrame#barraEdicion QLabel { background: transparent; }
QToolButton#baldosaMenu { background: rgba(255,255,255,0.08); color: #A3A3A3; border: none; border-radius: 11px;
    min-width: 24px; max-width: 24px; min-height: 22px; max-height: 22px; padding: 0; font-size: 14px; font-weight: 700; }
QToolButton#baldosaMenu:hover { background: rgba(255,255,255,0.16); color: #FFFFFF; }
QToolButton#baldosaQuitar { background: #F87171; color: #04130E; border: none; border-radius: 11px;
    min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; padding: 0; font-size: 15px; font-weight: 700; }
QToolButton#baldosaQuitar:hover { background: #7A2A24; color: #FFFFFF; }
QFrame#marcadorDestino { background: rgba(255,255,255,0.05); border: 2px dashed #2F6B57; border-radius: 14px; }
QFrame#itemCatalogo { background: #0F0F0F; border: 1px solid #232323; border-radius: 12px; }
QFrame#itemCatalogo QLabel { background: transparent; }
QPushButton#categoriaCatalogo { text-align: left; padding: 8px 12px; border: none; background: transparent; color: #A3A3A3; }
QPushButton#categoriaCatalogo:hover { background: rgba(255,255,255,0.06); color: #FFFFFF; }
QPushButton#categoriaCatalogo:checked { background: #10261F; color: #34D399; }
QToolButton#tipoGrafico { background: transparent; border: 1px solid #2E2E2E; border-radius: 10px; padding: 0; }
QToolButton#tipoGrafico:hover { border-color: #4A4A4A; background: transparent; }
QToolButton#tipoGrafico:checked { border: 2px solid #10B981; background: #10261F; }
QFrame#modalCaja QDateEdit, QFrame#modalCaja QSpinBox, QFrame#modalCaja QLineEdit, QFrame#modalCaja QComboBox {
    min-height: 18px; padding: 6px 10px; border: 1px solid #2E2E2E; border-radius: 8px; background: #111111; }
QFrame#modalCaja QLineEdit:focus, QFrame#modalCaja QComboBox:focus, QFrame#modalCaja QSpinBox:focus,
QFrame#modalCaja QDateEdit:focus { border: 1px solid #10B981; }

/* Acabado común: estado vacío de tablas, deslizadores y diálogos */
QLabel#tablaVacia { color: #8A8A8A; background: transparent; font-size: 12px; }
QSlider::groove:horizontal { height: 4px; background: #232323; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #10B981; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; height: 14px; margin: -6px 0; border-radius: 8px; background: #10B981;
                             border: 2px solid #111111; }
QSlider::handle:horizontal:hover { background: #34D399; }
QDialog QLabel { color: #CFCFCF; }
QDialog QPushButton { min-width: 88px; }
QInputDialog QLineEdit { min-width: 280px; }

/* Perfil */
QWidget#filaIcono { background: transparent; }
QLabel#perfilNombre { font-size: 20px; font-weight: 700; background: transparent; }
QLabel#tituloTarjeta { font-size: 15px; font-weight: 700; background: transparent; }
QFrame#separadorSuave { background: #232323; border: none; }
QFrame#lienzo QFrame#segmentado { background: #0F0F0F; border: 1px solid #232323; border-radius: 12px; }
QFrame#lienzo QFrame#segmentado QPushButton#segmento { border: 1px solid transparent; background: transparent; border-radius: 9px;
    padding: 7px 12px; color: #A3A3A3; font-weight: 600; min-height: 18px; }
QFrame#lienzo QFrame#segmentado QPushButton#segmento:hover { color: #FFFFFF; background: rgba(255,255,255,0.05); }
QFrame#lienzo QFrame#segmentado QPushButton#segmento:checked { background: #1C1C1C; color: #FFFFFF; border: 1px solid #2E2E2E; }

/* Pantalla Sincronización: superficies de 20/14 px, segmentos y tabla ligera */
QFrame#tarjetaSync { background: #111111; border: 1px solid #232323; border-radius: 20px; }
QFrame#tarjetaSync QLabel { background: transparent; }
QFrame#contadorSync { background: #0F0F0F; border: 1px solid #232323; border-radius: 14px; }
QFrame#contadorSync:hover { border-color: #2E2E2E; background: #121212; }
QFrame#contadorSync QLabel { background: transparent; }
QFrame#divisorSync { background: #232323; border: none; max-width: 1px; min-width: 1px; }
QLabel#tituloSync { font-size: 26px; font-weight: 700; color: #FFFFFF; background: transparent; }
QLabel#estadoHeroSync { font-size: 22px; font-weight: 700; color: #FFFFFF; background: transparent; }
QLabel#valorStatSync { font-size: 19px; font-weight: 700; color: #FFFFFF; background: transparent; }
QLabel#codigoSync { background: transparent; }
QLabel#badgeSync { background: #3A1512; color: #F87171; border-radius: 11px; padding: 3px 11px; font-size: 12px;
                   font-weight: 600; }
QLabel#badgeSync[vacio="true"] { background: #10261F; color: #34D399; }
QProgressBar#progresoSync { min-height: 3px; max-height: 3px; border: none; border-radius: 1px; background: #1C1C1C; }
QProgressBar#progresoSync::chunk { background: #10B981; border-radius: 1px; }
QFrame#lienzo QPushButton#segmento { min-height: 16px; padding: 5px 13px; border-radius: 13px; background: transparent;
                                     border: 1px solid transparent; color: #A3A3A3; font-weight: 600; }
QFrame#lienzo QPushButton#segmento:hover { background: #1C1C1C; color: #EDEDED; }
QFrame#lienzo QPushButton#segmento:checked { background: #10261F; color: #34D399; border-color: #1E3A32; }
QFrame#lienzo QPushButton#accionSync { border-radius: 15px; padding: 5px 15px 5px 11px; min-height: 18px; }
QTableWidget#tablaSync { background: transparent; border: none; gridline-color: transparent; outline: none; }
QTableWidget#tablaSync QHeaderView { background: transparent; }
QTableWidget#tablaSync QHeaderView::section { background: transparent; border: none; border-bottom: 1px solid #232323;
                                              padding: 8px 14px; color: #8A8A8A; font-size: 11px; font-weight: 600; }
QTableWidget#tablaSync::item { border: none; }
QFrame#tarjetaSync QStackedWidget, QWidget#vacioSync { background: transparent; }
"""


_FLECHAS: dict[str, str] = {}


def estilo() -> str:
    """``ESTILO`` más las flechas de los desplegables y de los campos numéricos.

    Qt deja de dibujar esas flechas en cuanto un control lleva hoja de estilo, y solo acepta una imagen: se pintan
    una vez (necesita la ``QApplication`` ya creada) en una carpeta temporal y se referencian desde aquí.
    """
    if not _FLECHAS:
        carpeta = Path(tempfile.mkdtemp(prefix="inventario-estilo-"))
        for nombre, puntos in (("abajo", ((3, 5), (7, 9), (11, 5))), ("arriba", ((3, 9), (7, 5), (11, 9)))):
            imagen = QPixmap(14, 14)
            imagen.fill(Qt.GlobalColor.transparent)
            pintor = QPainter(imagen)
            pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
            pintor.setPen(QPen(QColor("#8A8A8A"), 1.8, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
            pintor.drawPolyline(*[QPointF(x, y) for x, y in puntos])
            pintor.end()
            ruta = carpeta / f"{nombre}.png"
            imagen.save(str(ruta))
            _FLECHAS[nombre] = ruta.as_posix()
        palomita = QPixmap(16, 16)
        palomita.fill(Qt.GlobalColor.transparent)
        pintor = QPainter(palomita)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(QPen(QColor("#04130E"), 2.0, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
        pintor.drawPolyline(QPointF(3.8, 8.4), QPointF(6.7, 11.2), QPointF(12.2, 4.8))
        pintor.end()
        ruta = carpeta / "palomita.png"
        palomita.save(str(ruta))
        _FLECHAS["palomita"] = ruta.as_posix()
    return ESTILO + f"""
QCheckBox::indicator:checked {{ image: url({_FLECHAS["palomita"]}); }}
QComboBox::down-arrow {{ image: url({_FLECHAS["abajo"]}); width: 14px; height: 14px; margin-right: 8px; }}
QSpinBox::up-arrow {{ image: url({_FLECHAS["arriba"]}); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url({_FLECHAS["abajo"]}); width: 10px; height: 10px; }}
"""


class RefreshableView(Protocol):
    """Lo que ``MainWindow.add_view`` espera de una pestaña (además de ser un QWidget)."""

    def refresh(self) -> None:
        """Vuelve a consultar y repinta. Nunca bloquea la interfaz."""


class _Entrega(QObject):
    """Vive en el hilo de la interfaz: recibe lo que termina un worker y lo pasa al runner."""

    def __init__(self, runner: "QueryRunner", worker: QueryWorker, key, token, on_done, on_error) -> None:
        super().__init__(runner)
        self.runner, self.worker, self.key, self.token = runner, worker, key, token
        self.on_done, self.on_error = on_done, on_error

    @pyqtSlot(object)
    def exito(self, resultado) -> None:
        if not _vivo(self.runner):
            return
        self.runner._terminar(self, self.on_done, resultado)

    @pyqtSlot(str)
    def fallo(self, mensaje: str) -> None:
        if not _vivo(self.runner):
            return
        self.runner._terminar(self, self.on_error, mensaje)


def _vivo(objeto: QObject) -> bool:
    """Si ``objeto`` y su dueño siguen existiendo en Qt (una ventana cerrada con consultas en curso ya no)."""
    if sip.isdeleted(objeto):
        return False
    dueno = objeto.parent()
    return dueno is None or not sip.isdeleted(dueno)


MAX_HILOS = 8


class QueryRunner(QObject):
    """Ejecuta funciones (consultas a Oracle) en el pool de hilos y entrega el resultado en la UI.

    Con ``key``, solo cuenta la última llamada de esa clave: un resultado viejo que llega tarde
    (por un refresco más reciente) se descarta.
    """

    def __init__(self, parent: QObject | None = None, pool: QThreadPool | None = None) -> None:
        super().__init__(parent)
        self._pool = pool or QThreadPool.globalInstance()
        if pool is None:
            # Cada hilo guarda su conexión a Oracle (db._obtener): hilos fijos y pocos, para que no se abran y cierren
            # conexiones sin parar (la XE 11g responde ORA-12516 si se abren muy seguido).
            self._pool.setExpiryTimeout(-1)
            self._pool.setMaxThreadCount(min(self._pool.maxThreadCount(), MAX_HILOS))
        self._activos: dict[int, tuple[QueryWorker, _Entrega]] = {}
        self._ultimo: dict[str, int] = {}
        self._token = 0

    @property
    def pendientes(self) -> int:
        return len(self._activos)

    def run(self, fn: Callable, on_done: Callable, on_error: Callable | None = None, *args,
            key: str | None = None, **kwargs) -> QueryWorker:
        self._token += 1
        if key is not None:
            self._ultimo[key] = self._token
        worker = QueryWorker(fn, *args, **kwargs)
        entrega = _Entrega(self, worker, key, self._token, on_done, on_error)
        self._activos[id(worker)] = (worker, entrega)  # se conservan hasta entregar (las señales deben llegar)
        worker.signals.finished.connect(entrega.exito)
        worker.signals.failed.connect(entrega.fallo)
        self._pool.start(worker)
        return worker

    def _terminar(self, entrega: _Entrega, callback: Callable | None, valor) -> None:
        self._activos.pop(id(entrega.worker), None)
        if entrega.key is not None and self._ultimo.get(entrega.key) != entrega.token:
            return  # llegó tarde: ya hay una consulta más reciente
        if callback is not None:
            try:
                callback(valor)
            except RuntimeError as exc:
                # La pantalla se cerró mientras llegaba el resultado: sus widgets ya no existen. Nada que mostrar.
                if "has been deleted" not in str(exc):
                    raise


class StateBanner(QFrame):
    """Estado de una vista: «Cargando…» o «Sin datos» en una línea discreta; los errores de BD van a la Isla con un
    botón «Reintentar» (``retry``)."""

    retry = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("estadoVista")
        self._clave = f"consulta-{id(self)}"
        self._con_error = False
        self._label = QLabel()
        self._label.setObjectName("estadoVistaTexto")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 6)
        lay.addWidget(self._label, 1)
        self.btn_reintentar = QPushButton(t("Reintentar"), self)
        self.btn_reintentar.clicked.connect(self.retry)
        self.btn_reintentar.hide()
        self._barrido = BarridoCarga(self)
        self.hide()

    def text(self) -> str:
        return self._label.text()

    def registrar(self, texto: str) -> None:
        """Guarda el texto del estado sin mostrarlo (quien lo llama ya lo comunicó por la Isla)."""
        self._label.setText(texto)

    def _linea(self, texto: str) -> None:
        self._label.setText(texto)
        self.show()

    def show_loading(self) -> None:
        self._linea(t("Cargando…"))
        self._barrido.iniciar()   # el barrido dura exactamente lo que dura la consulta

    def show_empty(self, texto: str = "Sin datos") -> None:
        self._barrido.detener()
        self._linea(t(texto))

    def show_error(self, mensaje: str) -> None:
        self._barrido.detener()
        self._label.setText(t("No se pudo consultar la base de datos: {mensaje}", mensaje=mensaje))
        self.hide()
        self._con_error = True
        isla.error(t("No se pudo consultar la base de datos"), mensaje, clave=self._clave,
                   accion=(t("Reintentar"), self.retry.emit))

    def clear(self) -> None:
        self._barrido.detener()
        self.hide()
        if self._con_error:
            self._con_error = False
            isla.cerrar(clave=self._clave)
