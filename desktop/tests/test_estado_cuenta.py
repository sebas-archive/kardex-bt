"""Pantalla de una cuenta sin acceso: PENDIENTE o RECHAZADA (el Administrador nunca llega aquí)."""

from datetime import datetime

import pytest
from PyQt6.QtWidgets import QPushButton

from app.auth import PENDIENTE, RECHAZADO, SUSPENDIDO, CuentaSinAcceso
from app.views.estado_cuenta import EstadoCuentaView

REGISTRO = datetime(2026, 11, 13, 9, 30)


def _vista(qtbot, estado, motivo=None):
    vista = EstadoCuentaView()
    qtbot.addWidget(vista)
    vista.show()
    vista.mostrar(CuentaSinAcceso("luis", "Luis Ortiz", estado, motivo, REGISTRO))
    return vista


def _botones(vista):
    return [b.text() for b in vista.findChildren(QPushButton) if b.isVisible()]


def test_pendiente_muestra_espera_y_volver(qtbot):
    vista = _vista(qtbot, PENDIENTE)
    assert vista.lbl_estado.text() == "Pendiente"
    assert vista.lbl_mensaje.text() == "Tu cuenta espera aprobación del administrador"
    assert (vista.lbl_nombre.text(), vista.lbl_usuario.text()) == ("Luis Ortiz", "@luis")
    assert "13/11/2026" in vista.lbl_fecha.text()
    assert vista.lbl_motivo.isHidden()
    assert _botones(vista) == ["Volver al acceso"]


@pytest.mark.parametrize("estado", [RECHAZADO, SUSPENDIDO])
def test_rechazado_y_suspendido_muestran_motivo(qtbot, estado):
    vista = _vista(qtbot, estado, "No trabaja en la bodega")
    assert vista.lbl_estado.text() in ("Rechazada", "Suspendida")
    assert vista.lbl_motivo.text() == "Motivo: No trabaja en la bodega"
    assert _botones(vista) == ["Volver al acceso"]


def test_el_boton_emite_volver(qtbot):
    vista = _vista(qtbot, RECHAZADO, "x")
    with qtbot.waitSignal(vista.volver, timeout=1000):
        vista.btn_volver.click()
