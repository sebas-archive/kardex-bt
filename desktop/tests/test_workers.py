"""QueryWorker: las consultas corren fuera del hilo de la interfaz."""

import threading

from PyQt6.QtCore import QThread, QThreadPool

from app import db as dbq
from app.workers import QueryWorker


def run(worker):
    QThreadPool.globalInstance().start(worker)


def test_worker_emits_failed_on_oracle_error(qtbot, monkeypatch):
    monkeypatch.setenv("DB_DSN", "127.0.0.1:1/XE")  # nadie escucha: ORA-12541 real, no un mock
    worker = QueryWorker(dbq.fetch_resumen)
    finished = []
    worker.signals.finished.connect(finished.append)
    with qtbot.waitSignal(worker.signals.failed, timeout=20000) as blocker:
        run(worker)
    assert "ORA-" in blocker.args[0]
    assert finished == []


def test_worker_emits_finished_with_the_result(qtbot, escenario):
    worker = QueryWorker(dbq.fetch_resumen)
    with qtbot.waitSignal(worker.signals.finished, timeout=20000) as blocker:
        run(worker)
    assert blocker.args[0].id_conteo == "ACTUAL"


def test_worker_runs_the_function_off_the_ui_thread(qtbot, qapp):
    seen = {}

    def whoami(x, y=0):
        seen["thread"] = threading.current_thread()
        seen["qt_thread"] = QThread.currentThread()
        return x + y

    worker = QueryWorker(whoami, 40, y=2)
    with qtbot.waitSignal(worker.signals.finished, timeout=5000) as blocker:
        run(worker)
    assert blocker.args == [42]
    assert seen["thread"] is not threading.main_thread()
    assert seen["qt_thread"] != qapp.thread()


def test_las_consultas_reutilizan_la_conexion_de_su_hilo(qtbot, monkeypatch):
    """PyQt crea y destruye el estado de Python de un hilo del pool en cada tarea, así que ``threading.local``
    se pierde entre consultas: cada una abría otra conexión (cientos por minuto) y la XE terminaba respondiendo
    ORA-12516. La conexión debe sobrevivir entre tareas del mismo hilo."""
    from PyQt6.QtCore import QThreadPool

    from app import db
    from app.views.base import QueryRunner

    abiertas = []
    original = db.connect_oracle
    monkeypatch.setattr(db, "connect_oracle", lambda *a: (abiertas.append(1), original(*a))[1])
    runner = QueryRunner()
    hechas = []
    for _ in range(10):
        runner.run(lambda: db.fetch_resumen(), lambda r: hechas.append(r))
        qtbot.waitUntil(lambda n=len(hechas): len(hechas) == n + 1, timeout=10000)
    assert len(abiertas) <= 2                  # consultas una tras otra: uno o dos hilos del pool, no diez conexiones
    assert QThreadPool.globalInstance().maxThreadCount() <= 8


def test_un_resultado_tardio_no_llega_a_una_pantalla_ya_destruida(qtbot):
    """Al cerrar una ventana con consultas en curso, sus resultados llegaban a widgets ya borrados (RuntimeError y,
    a veces, un segfault de Qt). El runner los descarta si su dueño ya no existe."""
    import threading

    from PyQt6 import sip
    from PyQt6.QtWidgets import QWidget

    from app.views.base import QueryRunner

    dueno = QWidget()
    runner = QueryRunner(dueno)
    soltar, recibidos = threading.Event(), []
    runner.run(lambda: soltar.wait(5) or "tarde", recibidos.append, recibidos.append)
    sip.delete(dueno)                       # la ventana se cierra mientras la consulta sigue
    soltar.set()
    qtbot.wait(300)
    assert recibidos == []
