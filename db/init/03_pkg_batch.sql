-- Batch de inventario: pasa las lecturas del staging (CAPTURA_TRANSITO) a REGISTROS_PROCESADOS.
-- El contenedor ejecuta este script como SYS; el paquete vive en el esquema APP.
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
SET DEFINE OFF
ALTER SESSION SET CURRENT_SCHEMA = app;

CREATE OR REPLACE PACKAGE pkg_batch AS
    -- Procesa todo lo PENDIENTE. Las filas que llevan mas de p_timeout_min minutos en
    -- PROCESANDO (una corrida que murio a medias) se recuperan primero.
    PROCEDURE procesar_pendientes(
        p_origen      IN VARCHAR2 DEFAULT 'MANUAL',
        p_timeout_min IN NUMBER   DEFAULT 5
    );

    -- Devuelve a PENDIENTE las filas en ERROR (de un conteo, o todas) y las vuelve a procesar.
    PROCEDURE reprocesar_errores(p_id_conteo IN VARCHAR2 DEFAULT NULL);

    -- Borra del staging las filas PROCESADO con mas de p_dias dias.
    PROCEDURE purgar_transito(p_dias IN NUMBER DEFAULT 7);
END pkg_batch;
/

CREATE OR REPLACE PACKAGE BODY pkg_batch AS

    e_validacion EXCEPTION;
    g_error      VARCHAR2(40);   -- codigo de la ultima validacion fallida

    PROCEDURE fallar(p_codigo IN VARCHAR2) IS
    BEGIN
        g_error := p_codigo;
        RAISE e_validacion;
    END fallar;

    -- Campo n (1 = 'REC') de una linea del protocolo; tolera campos vacios.
    FUNCTION campo(p_raw IN VARCHAR2, p_n IN PLS_INTEGER) RETURN VARCHAR2 IS
    BEGIN
        RETURN REGEXP_SUBSTR(p_raw, '([^|]*)(\||$)', 1, p_n, NULL, 1);
    END campo;

    -- Deshace la codificacion de texto libre del protocolo (%25 %7C %0D %0A).
    FUNCTION texto(p_valor IN VARCHAR2) RETURN VARCHAR2 IS
    BEGIN
        IF p_valor IS NULL THEN
            RETURN NULL;
        END IF;
        RETURN UTL_URL.UNESCAPE(p_valor, 'UTF-8');
    END texto;

    -- D13: en cada (conteo, ubicacion, SKU) vale la lectura con FECHA_CAPTURA mas reciente;
    -- si empatan, la de ID_TRANSITO mayor (global, asignado al llegar al staging).
    PROCEDURE recalcular_vigente(p_conteo IN VARCHAR2, p_ubic IN VARCHAR2, p_sku IN VARCHAR2) IS
        l_mejor registros_procesados.id_registro%TYPE;
    BEGIN
        SELECT id_registro
          INTO l_mejor
          FROM (SELECT id_registro
                  FROM registros_procesados
                 WHERE id_conteo = p_conteo AND cod_ubicacion = p_ubic AND sku = p_sku
                 ORDER BY fecha_captura DESC, NVL(id_transito, -1) DESC, id_registro DESC)
         WHERE ROWNUM = 1;

        UPDATE registros_procesados
           SET vigente = CASE WHEN id_registro = l_mejor THEN 'S' ELSE 'N' END
         WHERE id_conteo = p_conteo AND cod_ubicacion = p_ubic AND sku = p_sku
           AND vigente <> CASE WHEN id_registro = l_mejor THEN 'S' ELSE 'N' END;
    END recalcular_vigente;

    -- Valida una linea REC y la inserta. Lanza e_validacion (con g_error) si no es valida.
    PROCEDURE procesar_fila(p_id IN NUMBER, p_raw IN VARCHAR2) IS
        l_ts      VARCHAR2(4000);
        l_conteo  VARCHAR2(4000);
        l_ubic    VARCHAR2(4000);
        l_sku     VARCHAR2(4000);
        l_cant    VARCHAR2(4000);
        l_oper    VARCHAR2(4000);
        l_nota    VARCHAR2(4000);
        l_n       PLS_INTEGER;
    BEGIN
        l_ts := campo(p_raw, 3);
        IF campo(p_raw, 1) IS NULL OR campo(p_raw, 1) <> 'REC'
           OR l_ts IS NULL OR NOT REGEXP_LIKE(l_ts, '^[0-9]{1,15}$') THEN
            fallar('FORMATO_INVALIDO');
        END IF;
        l_conteo := texto(campo(p_raw, 4));
        l_ubic   := texto(campo(p_raw, 5));
        l_sku    := texto(campo(p_raw, 6));
        l_cant   := texto(campo(p_raw, 7));
        l_oper   := texto(campo(p_raw, 8));
        l_nota   := texto(campo(p_raw, 9));

        SELECT COUNT(*) INTO l_n FROM conteos WHERE id_conteo = l_conteo AND estado = 'ABIERTO';
        IF l_n = 0 THEN
            fallar('CONTEO_NO_ABIERTO');
        END IF;
        SELECT COUNT(*) INTO l_n FROM ubicaciones WHERE cod_ubicacion = l_ubic;
        IF l_n = 0 THEN
            fallar('UBICACION_DESCONOCIDA');
        END IF;
        SELECT COUNT(*) INTO l_n FROM productos WHERE sku = l_sku;
        IF l_n = 0 THEN
            fallar('SKU_DESCONOCIDO');
        END IF;
        -- Decimal con punto, sin signo, hasta 9 enteros y 3 decimales.
        IF l_cant IS NULL OR NOT REGEXP_LIKE(l_cant, '^[0-9]{1,9}(\.[0-9]{1,3})?$') THEN
            fallar('CANTIDAD_INVALIDA');
        END IF;

        INSERT INTO registros_procesados
            (id_transito, id_conteo, cod_ubicacion, sku, cantidad, operador, nota, fecha_captura, vigente)
        VALUES
            (p_id, l_conteo, l_ubic, l_sku,
             -- Mascara fija: no depende del NLS de la sesion.
             TO_NUMBER(l_cant, '999999999D999', 'NLS_NUMERIC_CHARACTERS=''.,'''),
             SUBSTR(l_oper, 1, 60), SUBSTR(l_nota, 1, 255),
             -- epoch_ms -> TIMESTAMP en UTC.
             TIMESTAMP '1970-01-01 00:00:00' + NUMTODSINTERVAL(TO_NUMBER(l_ts) / 1000, 'SECOND'),
             'N');

        recalcular_vigente(l_conteo, l_ubic, l_sku);
    END procesar_fila;

    PROCEDURE procesar_pendientes(
        p_origen      IN VARCHAR2 DEFAULT 'MANUAL',
        p_timeout_min IN NUMBER   DEFAULT 5
    ) IS
        TYPE t_ids IS TABLE OF captura_transito.id_transito%TYPE;
        l_ids     t_ids;
        l_inicio  TIMESTAMP := SYSTIMESTAMP;
        l_raw     captura_transito.datos_raw%TYPE;
        l_msg     VARCHAR2(400);
        l_ok      PLS_INTEGER := 0;
        l_err     PLS_INTEGER := 0;
    BEGIN
        -- 1. Recuperar huerfanas: una corrida anterior las reclamo y no termino.
        UPDATE captura_transito
           SET estado = 'PENDIENTE', fecha_reclamo = NULL
         WHERE estado = 'PROCESANDO'
           AND fecha_reclamo < SYSTIMESTAMP - NUMTODSINTERVAL(p_timeout_min, 'MINUTE');

        -- 2. Reclamar en un unico UPDATE. Dos corridas simultaneas nunca reclaman la misma fila:
        --    la segunda espera el COMMIT de la primera y ya no las ve PENDIENTE.
        UPDATE captura_transito
           SET estado = 'PROCESANDO', fecha_reclamo = SYSTIMESTAMP
         WHERE estado = 'PENDIENTE'
        RETURNING id_transito BULK COLLECT INTO l_ids;
        COMMIT;

        IF l_ids.COUNT = 0 THEN
            RETURN;  -- nada que hacer: no se escribe bitacora (el job corre cada 60 s)
        END IF;

        -- 3. Procesar. El bloqueo serializa el recalculo de VIGENTE entre corridas
        --    simultaneas; las consultas de la aplicacion no se bloquean.
        LOCK TABLE registros_procesados IN EXCLUSIVE MODE;
        FOR i IN 1 .. l_ids.COUNT LOOP
            BEGIN
                SELECT datos_raw INTO l_raw FROM captura_transito WHERE id_transito = l_ids(i);
            EXCEPTION
                WHEN NO_DATA_FOUND THEN
                    CONTINUE;  -- la fila desaparecio entre el reclamo y ahora
            END;

            SAVEPOINT sp_fila;
            BEGIN
                procesar_fila(l_ids(i), l_raw);
                UPDATE captura_transito
                   SET estado = 'PROCESADO', mensaje_error = NULL
                 WHERE id_transito = l_ids(i);
                l_ok := l_ok + 1;
            EXCEPTION
                WHEN e_validacion THEN
                    ROLLBACK TO sp_fila;
                    UPDATE captura_transito
                       SET estado = 'ERROR', mensaje_error = g_error
                     WHERE id_transito = l_ids(i);
                    l_err := l_err + 1;
                WHEN DUP_VAL_ON_INDEX THEN
                    -- Red de seguridad (UNIQUE sobre ID_TRANSITO): otra corrida ya la proceso.
                    ROLLBACK TO sp_fila;
                    UPDATE captura_transito
                       SET estado = 'PROCESADO', mensaje_error = NULL
                     WHERE id_transito = l_ids(i);
                WHEN OTHERS THEN
                    l_msg := SUBSTR(SQLERRM, 1, 400);
                    ROLLBACK TO sp_fila;
                    UPDATE captura_transito
                       SET estado = 'ERROR', mensaje_error = l_msg
                     WHERE id_transito = l_ids(i);
                    l_err := l_err + 1;
            END;

            IF MOD(i, 100) = 0 THEN
                COMMIT;
                LOCK TABLE registros_procesados IN EXCLUSIVE MODE;
            END IF;
        END LOOP;

        -- 5. Bitacora de la corrida.
        INSERT INTO log_batch (inicio, fin, procesados, errores, origen)
        VALUES (l_inicio, SYSTIMESTAMP, l_ok, l_err, SUBSTR(p_origen, 1, 20));
        COMMIT;
    END procesar_pendientes;

    PROCEDURE reprocesar_errores(p_id_conteo IN VARCHAR2 DEFAULT NULL) IS
    BEGIN
        -- El conteo es el campo 4 de la linea guardada (los IDs de conteo no llevan escapes).
        UPDATE captura_transito
           SET estado = 'PENDIENTE', mensaje_error = NULL, fecha_reclamo = NULL
         WHERE estado = 'ERROR'
           AND (p_id_conteo IS NULL
                OR REGEXP_SUBSTR(datos_raw, '([^|]*)(\||$)', 1, 4, NULL, 1) = p_id_conteo);
        COMMIT;
        procesar_pendientes('REPROCESO');
    END reprocesar_errores;

    PROCEDURE purgar_transito(p_dias IN NUMBER DEFAULT 7) IS
    BEGIN
        -- Se conserva siempre la fila de mayor SEQ de cada dispositivo: de ella sale el
        -- READY|<ultimo_seq>; sin ella el telefono reenviaria todo su historial.
        DELETE FROM captura_transito t
         WHERE t.estado = 'PROCESADO'
           AND t.fecha_recepcion < SYSTIMESTAMP - NUMTODSINTERVAL(p_dias, 'DAY')
           AND t.seq < (SELECT MAX(u.seq)
                          FROM captura_transito u
                         WHERE u.uuid_dispositivo = t.uuid_dispositivo);
        COMMIT;
    END purgar_transito;

END pkg_batch;
/

-- Un paquete con errores de compilacion no debe pasar en silencio.
DECLARE
    l_errores PLS_INTEGER;
    l_detalle VARCHAR2(1000);
BEGIN
    SELECT COUNT(*), MAX(type || ' linea ' || line || ': ' || SUBSTR(text, 1, 400))
      INTO l_errores, l_detalle
      FROM all_errors
     WHERE owner = 'APP' AND name = 'PKG_BATCH';
    IF l_errores > 0 THEN
        RAISE_APPLICATION_ERROR(-20000, 'PKG_BATCH no compila: ' || l_detalle);
    END IF;
END;
/
