-- Batch de inventario: pasa las lecturas del staging (CAPTURA_TRANSITO) a REGISTROS_PROCESADOS
-- y concilia lo contado contra el stock del sistema (CONCILIACION).
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

    -- Recalcula CONCILIACION de un conteo (idempotente; hace COMMIT).
    PROCEDURE conciliar(p_id_conteo IN VARCHAR2);

    -- Procesa lo pendiente, cierra el conteo y lo concilia: lo que nadie conto pasa a contado 0.
    PROCEDURE cerrar_conteo(p_id_conteo IN VARCHAR2);

    -- Devuelve a PENDIENTE las filas en ERROR (de un conteo, o todas) y las vuelve a procesar.
    PROCEDURE reprocesar_errores(p_id_conteo IN VARCHAR2 DEFAULT NULL);

    -- Borra del staging las filas PROCESADO con mas de p_dias dias.
    PROCEDURE purgar_transito(p_dias IN NUMBER DEFAULT 7);
END pkg_batch;
/

CREATE OR REPLACE PACKAGE BODY pkg_batch AS

    e_validacion EXCEPTION;
    g_error      VARCHAR2(40);   -- codigo de la ultima validacion fallida

    TYPE t_conteos IS TABLE OF BOOLEAN INDEX BY VARCHAR2(120);
    g_conteos    t_conteos;      -- conteos que recibieron lecturas en la corrida actual

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

    -- D13: en cada (conteo, SKU) vale la lectura con FECHA_CAPTURA mas reciente (recontar reemplaza);
    -- si empatan, la de ID_TRANSITO mayor (global, asignado al llegar al staging).
    PROCEDURE recalcular_vigente(p_conteo IN VARCHAR2, p_sku IN VARCHAR2) IS
        l_mejor registros_procesados.id_registro%TYPE;
    BEGIN
        SELECT id_registro
          INTO l_mejor
          FROM (SELECT id_registro
                  FROM registros_procesados
                 WHERE id_conteo = p_conteo AND sku = p_sku
                 ORDER BY fecha_captura DESC, NVL(id_transito, -1) DESC, id_registro DESC)
         WHERE ROWNUM = 1;

        UPDATE registros_procesados
           SET vigente = CASE WHEN id_registro = l_mejor THEN 'S' ELSE 'N' END
         WHERE id_conteo = p_conteo AND sku = p_sku
           AND vigente <> CASE WHEN id_registro = l_mejor THEN 'S' ELSE 'N' END;
    END recalcular_vigente;

    -- Valida una linea REC y la inserta. Lanza e_validacion (con g_error) si no es valida.
    PROCEDURE procesar_fila(p_id IN NUMBER, p_raw IN VARCHAR2) IS
        l_ts      VARCHAR2(4000);
        l_conteo  VARCHAR2(4000);
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
        l_sku    := texto(campo(p_raw, 5));
        l_cant   := texto(campo(p_raw, 6));
        l_oper   := texto(campo(p_raw, 7));
        l_nota   := texto(campo(p_raw, 8));

        SELECT COUNT(*) INTO l_n FROM conteos WHERE id_conteo = l_conteo AND estado = 'ABIERTO';
        IF l_n = 0 THEN
            fallar('CONTEO_NO_ABIERTO');
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
            (id_transito, id_conteo, sku, cantidad, operador, nota, fecha_captura, vigente)
        VALUES
            (p_id, l_conteo, l_sku,
             -- Mascara fija: no depende del NLS de la sesion.
             TO_NUMBER(l_cant, '999999999D999', 'NLS_NUMERIC_CHARACTERS=''.,'''),
             SUBSTR(l_oper, 1, 60), SUBSTR(l_nota, 1, 255),
             -- epoch_ms -> TIMESTAMP en UTC.
             TIMESTAMP '1970-01-01 00:00:00' + NUMTODSINTERVAL(TO_NUMBER(l_ts) / 1000, 'SECOND'),
             'N');

        recalcular_vigente(l_conteo, l_sku);
        g_conteos(l_conteo) := TRUE;
    END procesar_fila;

    -- Reglas de conciliacion (por SKU del conteo):
    --   * Entran los SKU de la foto de stock y los que tienen lecturas vigentes (sin foto: sistema 0).
    --   * contada = la lectura vigente del SKU (una por conteo: recontar reemplaza); DIFERENCIA = contada - sistema.
    --   * OK si |DIFERENCIA| <= sistema x TOLERANCIA_PCT / 100 (limite inclusivo);
    --     si no, FALTANTE (contada < sistema) o SOBRANTE.
    --   * Sin lecturas: SIN_CONTAR mientras el conteo esta ABIERTO; al cerrarlo cuenta como 0.
    PROCEDURE conciliar_interno(p_id_conteo IN VARCHAR2) IS
        l_abierto PLS_INTEGER;
    BEGIN
        -- Serializa conciliaciones simultaneas (dos corridas, o corrida + cierre).
        LOCK TABLE conciliacion IN EXCLUSIVE MODE;

        SELECT COUNT(*) INTO l_abierto
          FROM conteos WHERE id_conteo = p_id_conteo AND estado = 'ABIERTO';

        DELETE FROM conciliacion WHERE id_conteo = p_id_conteo;

        INSERT INTO conciliacion
            (id_conteo, sku, cant_sistema, cant_contada, diferencia, diferencia_pct,
             valor_diferencia, clasificacion, fecha_calculo)
        SELECT p_id_conteo, x.sku, x.sistema, x.contada,
               CASE WHEN x.sin_contar = 1 THEN NULL ELSE x.contada - x.sistema END,
               CASE WHEN x.sin_contar = 1 OR x.sistema = 0 THEN NULL
                    ELSE GREATEST(-99999999.99,
                         LEAST(99999999.99, ROUND((x.contada - x.sistema) / x.sistema * 100, 2)))
               END,
               CASE WHEN x.sin_contar = 1 THEN NULL
                    ELSE ROUND((x.contada - x.sistema) * p.costo_unit, 2)
               END,
               CASE WHEN x.sin_contar = 1 THEN 'SIN_CONTAR'
                    WHEN ABS(x.contada - x.sistema) <= x.sistema * p.tolerancia_pct / 100 THEN 'OK'
                    WHEN x.contada < x.sistema THEN 'FALTANTE'
                    ELSE 'SOBRANTE'
               END,
               SYSTIMESTAMP
          FROM (SELECT k.sku,
                       NVL(s.cantidad_sistema, 0) AS sistema,
                       NVL(c.contada, 0)          AS contada,
                       CASE WHEN c.sku IS NULL AND l_abierto = 1 THEN 1 ELSE 0 END AS sin_contar
                  FROM (SELECT sku FROM stock_sistema WHERE id_conteo = p_id_conteo
                        UNION
                        SELECT sku FROM registros_procesados
                         WHERE id_conteo = p_id_conteo AND vigente = 'S') k
                  LEFT JOIN stock_sistema s
                         ON s.id_conteo = p_id_conteo AND s.sku = k.sku
                  LEFT JOIN (SELECT sku, SUM(cantidad) AS contada
                               FROM registros_procesados
                              WHERE id_conteo = p_id_conteo AND vigente = 'S'
                              GROUP BY sku) c
                         ON c.sku = k.sku) x
          JOIN productos p ON p.sku = x.sku;
    END conciliar_interno;

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
        l_conteo  VARCHAR2(120);
    BEGIN
        g_conteos.DELETE;

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

        -- 4. Bitacora de la corrida. Lo procesado queda confirmado aqui: un fallo al
        --    conciliar no debe devolver las filas a PROCESANDO.
        INSERT INTO log_batch (inicio, fin, procesados, errores, origen)
        VALUES (l_inicio, SYSTIMESTAMP, l_ok, l_err, SUBSTR(p_origen, 1, 20));
        COMMIT;

        -- 5. Conciliar cada conteo que recibio lecturas.
        l_conteo := g_conteos.FIRST;
        WHILE l_conteo IS NOT NULL LOOP
            conciliar_interno(l_conteo);
            l_conteo := g_conteos.NEXT(l_conteo);
        END LOOP;
        COMMIT;
    END procesar_pendientes;

    PROCEDURE conciliar(p_id_conteo IN VARCHAR2) IS
    BEGIN
        conciliar_interno(p_id_conteo);
        COMMIT;
    END conciliar;

    PROCEDURE cerrar_conteo(p_id_conteo IN VARCHAR2) IS
        l_existe PLS_INTEGER;
    BEGIN
        SELECT COUNT(*) INTO l_existe FROM conteos WHERE id_conteo = p_id_conteo;
        IF l_existe = 0 THEN
            RAISE_APPLICATION_ERROR(-20002, 'CONTEO_INEXISTENTE: ' || p_id_conteo);
        END IF;

        -- Lo recibido y aun sin procesar entra al conteo antes de cerrarlo;
        -- despues del cierre quedaria en ERROR (CONTEO_NO_ABIERTO).
        procesar_pendientes('CIERRE');

        -- Mismo bloqueo que el batch: ninguna corrida inserta lecturas mientras se cierra.
        LOCK TABLE registros_procesados IN EXCLUSIVE MODE;
        UPDATE conteos
           SET estado = 'CERRADO', fecha_cierre = SYSTIMESTAMP
         WHERE id_conteo = p_id_conteo AND estado = 'ABIERTO';
        conciliar_interno(p_id_conteo);
        COMMIT;
    END cerrar_conteo;

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

-- Estado inicial: cada conteo existente queda conciliado (todo SIN_CONTAR hasta la primera lectura).
BEGIN
    FOR c IN (SELECT id_conteo FROM conteos) LOOP
        pkg_batch.conciliar(c.id_conteo);
    END LOOP;
END;
/
