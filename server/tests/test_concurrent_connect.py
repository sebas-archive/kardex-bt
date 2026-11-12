"""Regresión: llamar a oracledb.connect() desde varios hilos a la vez aborta el proceso.

Con el modo thick (Instant Client 19 contra Oracle XE 11g) cuatro hilos conectando al mismo tiempo
terminan en «double free or corruption» / ORA-24550 y matan el intérprete (reproducido en 3 de 3
corridas de 40 rondas). Por eso corre en un subproceso: si alguien quita la serialización, falla
este test en vez de tumbar toda la suite.
"""

import subprocess
import sys
import textwrap

BURST = textwrap.dedent(
    """
    import os, threading, time
    from btsync.store import connect_oracle

    def one_round():
        barrier = threading.Barrier(4)
        conns = []

        def worker():
            barrier.wait(timeout=30)
            conns.append(connect_oracle(os.environ["DB_DSN"], os.environ["DB_USER"], os.environ["DB_PASSWORD"]))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(conns) == 4
        for c in conns:
            c.close()

    for _ in range(25):
        one_round()
        time.sleep(0.15)
    print("OK")
    """
)


def test_simultaneous_connects_from_four_threads_do_not_crash():
    result = subprocess.run(
        [sys.executable, "-c", BURST], capture_output=True, text=True, timeout=180
    )
    assert result.returncode == 0, f"el subproceso terminó con {result.returncode}:\n{result.stderr[-800:]}"
    assert result.stdout.strip() == "OK"
