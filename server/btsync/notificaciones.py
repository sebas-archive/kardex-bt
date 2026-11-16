"""Notificaciones: avisos de que algo pasó (un ajuste por aprobar, una sincronización recibida, stock bajo…).

**No son solicitudes:** una solicitud se aprueba o se rechaza en «Solicitudes»; una notificación solo se lee. Una
solicitud nueva genera, además, una notificación que lleva a esa pantalla.

Cada notificación va a un **rol** (la ven todas sus cuentas) o a un **usuario**. Quién la leyó vive en
``NOTIFICACIONES_LEIDAS`` (una fila por persona), así que leer no afecta a las demás. ``clave`` evita duplicados:
``(tipo, clave)`` es único. ``crear`` no confirma: va en la transacción del evento que la causa.
"""

from __future__ import annotations

import oracledb

from .store import ddl_tolerante

TABLA = "notificaciones"                 # las pruebas usan «notificaciones_tst»
TABLA_LEIDAS = "notificaciones_leidas"   # y «notificaciones_leidas_tst»


def migrar(conn) -> None:
    """Crea las tablas y la secuencia si faltan. Idempotente y tolerante a dos procesos a la vez."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM user_sequences WHERE sequence_name = 'SEQ_NOTIFICACIONES'")
    if not cur.fetchone()[0]:
        ddl_tolerante(cur, "CREATE SEQUENCE seq_notificaciones START WITH 1")
    cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :t", t=TABLA.upper())
    if not cur.fetchone()[0]:
        ddl_tolerante(cur, f"""CREATE TABLE {TABLA} (
            id       NUMBER             PRIMARY KEY,
            fecha    TIMESTAMP          DEFAULT SYSTIMESTAMP NOT NULL,
            tipo     VARCHAR2(30 CHAR)  NOT NULL,
            texto    VARCHAR2(300 CHAR) NOT NULL,
            seccion  VARCHAR2(40 CHAR),
            rol      VARCHAR2(12 CHAR),
            usuario  VARCHAR2(30 CHAR),
            clave    VARCHAR2(100 CHAR))""")
        # Único solo cuando hay clave: con UNIQUE (tipo, clave), Oracle trataría (tipo, NULL) como repetido.
        ddl_tolerante(cur, f"CREATE UNIQUE INDEX uq_{TABLA}_clave ON {TABLA} "
                           f"(CASE WHEN clave IS NOT NULL THEN tipo END, CASE WHEN clave IS NOT NULL THEN clave END)",
                      tambien=("ORA-00955",))
    cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :t", t=TABLA_LEIDAS.upper())
    if not cur.fetchone()[0]:
        ddl_tolerante(cur, f"""CREATE TABLE {TABLA_LEIDAS} (
            id_notificacion NUMBER            NOT NULL,
            usuario         VARCHAR2(30 CHAR) NOT NULL,
            CONSTRAINT pk_{TABLA_LEIDAS} PRIMARY KEY (id_notificacion, usuario))""")
    conn.commit()


def crear(cur, tipo: str, texto: str, seccion: str = "", rol: str | None = None, usuario: str | None = None,
          clave: str | None = None) -> bool:
    """Añade la notificación (sin commit). ``False`` si ya había una con ese ``(tipo, clave)``."""
    if (rol is None) == (usuario is None):
        raise ValueError("una notificación va a un rol o a un usuario")
    try:
        cur.execute(f"INSERT INTO {TABLA} (id, tipo, texto, seccion, rol, usuario, clave) "
                    f"VALUES (seq_notificaciones.NEXTVAL, :t, :x, :s, :r, :u, :k)",
                    t=tipo, x=texto[:300], s=seccion or None, r=rol, u=usuario, k=clave)
        return True
    except oracledb.IntegrityError as exc:
        if clave is not None and "ORA-00001" in str(exc):
            return False
        raise


def _lecturas(n: int) -> str:
    return f"{n} {'lectura' if n == 1 else 'lecturas'}"


def texto_sincronizacion(dispositivo: str, recibidos: int, errores: int) -> str:
    return (f"Sincronización recibida: {dispositivo}, {_lecturas(recibidos)}"
            + (f" · {errores} con error" if errores else ""))


def texto_nuevo_sku(sku: str) -> str:
    """El aviso de una lectura que espera la decisión del Administrador; «Ver» lleva a Sincronización."""
    return f"Nuevo SKU {sku}: decide «Crear y procesar» o «No crear» en Sincronización."


def _id_y_sku(fila) -> tuple[int, str]:
    """Acepta ``(id_transito, sku)`` o un objeto con esos atributos (p. ej. ``NuevoSkuFila`` del escritorio)."""
    if hasattr(fila, "id_transito"):
        return int(fila.id_transito), str(fila.sku or "")
    return int(fila[0]), str(fila[1] or "")


def avisar_nuevos_sku(cur, filas) -> int:
    """Deja en la CAMPANA/Notificaciones el aviso de cada lectura NUEVO_SKU pendiente. Sin COMMIT.

    La ``clave`` ``NUEVO_SKU:<id_transito>`` la hace idempotente: evaluarla otra vez no duplica nada.
    La usan ``Store.run_batch`` (el móvil sincronizó con la app cerrada) y el backfill del escritorio.
    Devuelve cuántas notificaciones se crearon de verdad.
    """
    creadas = 0
    for fila in filas:
        id_transito, sku = _id_y_sku(fila)
        if crear(cur, "NUEVO_SKU", texto_nuevo_sku(sku), "Sincronización", rol="ADMIN",
                 clave=f"NUEVO_SKU:{id_transito}"):
            creadas += 1
    return creadas
