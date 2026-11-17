"""Capturas adicionales de la aplicación real: Sincronización en otras resoluciones y Gráficas de Inventario.
Usa el mismo método que capturar_pantallas.py. Uso: python capturar_extra.py <carpeta_salida>"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("APP_SIN_ANIMACIONES", "1")

from PyQt6.QtTest import QTest              # noqa: E402
from PyQt6.QtWidgets import QApplication    # noqa: E402

SALIDA = Path(sys.argv[1])
CLAVE_DEMO = os.environ.get("CLAVE_DEMO", "Demo1234")


def guardar(widget, ruta: str) -> None:
    destino = SALIDA / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    pix = widget.grab()
    pix.save(str(destino), "PNG")
    print(destino, f"{pix.width()}x{pix.height()}")


def principal() -> int:
    app = QApplication(sys.argv)
    from app import auth, i18n
    from app.main import build_window
    from app.servicio_remoto import ServicioRemoto
    from app.views.base import estilo
    app.setStyleSheet(estilo())
    sesion = auth.iniciar_sesion("admin", CLAVE_DEMO)
    ventana = build_window(ServicioRemoto(), sesion=sesion)
    ventana.show()
    for ancho, alto in ((1366, 768), (1920, 1080)):
        ventana.resize(ancho, alto)
        ventana.ir_a(i18n.t("Sincronización"))
        QTest.qWait(3000)
        guardar(ventana, f"aplicacion/resoluciones/sincronizacion_{ancho}x{alto}.png")
    ventana.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
