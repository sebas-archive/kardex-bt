"""Fixtures de las pruebas de escritorio.

Reutilizan las del servidor (escenario fijo T-01, conexión, limpieza) en vez de duplicarlas:
una sola definición del escenario y de sus valores exactos.
"""

import importlib.util
from pathlib import Path

_SERVER_CONFTEST = Path(__file__).resolve().parents[2] / "server" / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location("server_conftest", _SERVER_CONFTEST)
server_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server_conftest)

# Fixtures (pytest las recoge por nombre desde este módulo).
escenario = server_conftest.escenario          # conteo T-01, ubicaciones U1-U3, SKUs A1-A5
scheduler_off = server_conftest.scheduler_off  # autouse: el job de 60 s no procesa a mitad de un test

# Utilidades para los tests: `from conftest import staging, connect`.
staging = server_conftest.staging
connect = server_conftest.connect
