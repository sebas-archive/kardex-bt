"""QueryWorker: las consultas corren fuera del hilo de la interfaz."""

import threading

from PyQt6.QtCore import QThread, QThreadPool

from app import db as dbq
from app.workers import QueryWorker


def run(worker):
    QThreadPool.globalInstance().start(worker)


def test_worker_emits_failed_on_oracle_error(qtbot, monkeypatch):
    monkeypatch.setenv("DB_DSN", "127.0.0.1:1/XE")  # nadie escucha: ORA-12541 real, no un mock
    worker = QueryWorker(dbq.fetch_conteos)
    finished = []
    worker.signals.finished.connect(finished.append)
    with qtbot.waitSignal(worker.signals.failed, timeout=20000) as blocker:
        run(worker)
    assert "ORA-" in blocker.args[0]
    assert finished == []


def test_worker_emits_finished_with_the_result(qtbot, escenario):
    worker = QueryWorker(dbq.fetch_resumen, "T-01")
    with qtbot.waitSignal(worker.signals.finished, timeout=20000) as blocker:
        run(worker)
    assert blocker.args[0].id_conteo == "T-01"


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
