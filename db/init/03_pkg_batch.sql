-- Batch de inventario continuo: pasa las lecturas del staging (CAPTURA_TRANSITO) a REGISTROS_PROCESADOS
-- y concilia lo contado contra el stock del sistema (CONCILIACION) del conteo unico ACTUAL.
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

    -- Recalcula CONCILIACION del conteo (idempotente; hace COMMIT).
    PROCEDURE conciliar(p_id_conteo IN VARCHAR2 DEFAULT 'ACTUAL');

    -- Devuelve a PENDIENTE las filas en ERROR y las vuelve a procesar.
    PROCEDURE reprocesar_errores(p_id_conteo IN VARCHAR2 DEFAULT NULL);

    -- Borra del staging las filas PROCESADO con mas de p_dias dias (la ultima de cada dispositivo se conserva).
    PROCEDURE purgar_transito(p_dias IN NUMBER DEFAULT 7);

    -- Alta de un SKU que llego en una lectura y no existe: producto + stock 0 en ACTUAL (hace COMMIT).
    -- La pantalla de Sincronizacion del Administrador la llama y despues reprocesa los errores.
    PROCEDURE alta_sku(
        p_sku       IN VARCHAR2,
        p_nombre    IN VARCHAR2,
        p_categoria IN VARCHAR2,
        p_unidad    IN VARCHAR2 DEFAULT 'UND',
        p_costo_unit IN NUMBER  DEFAULT 0
    );
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

    -- En cada SKU vale la lectura con FECHA_CAPTURA mas reciente (recontar reemplaza);
    -- si empatan, la de ID_TRANSITO mayor (global, asignado al llegar al staging).
    PROCEDURE recalcular_vigente(p_sku IN VARCHAR2) IS
        l_mejor registros_procesados.id_registro%TYPE;
    BEGIN
        BEGIN
            SELECT id_registro
              INTO l_mejor
              FROM (SELECT id_registro
                      FROM registros_procesados
                     WHERE id_conteo = 'ACTUAL' AND sku = p_sku
                     ORDER BY fecha_captura DESC, NVL(id_transito, -1) DESC, id_registro DESC)
             WHERE ROWNUM = 1;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                RETURN;
        END;

        UPDATE registros_procesados
           SET vigente = CASE WHEN id_registro = l_mejor THEN 'S' ELSE 'N' END
         WHERE id_conteo = 'ACTUAL' AND sku = p_sku
           AND vigente <> CASE WHEN id_registro = l_mejor THEN 'S' ELSE 'N' END;
    END recalcular_vigente;

    -- Valida una linea REC y la inserta. Lanza e_validacion (con g_error) si no es valida.
    PROCEDURE procesar_fila(p_id IN NUMBER, p_raw IN VARCHAR2) IS
        l_ts      VARCHAR2(4000);
        l_sku     VARCHAR2(4000);
        l_cant    VARCHAR2(4000);
        l_oper    VARCHAR2(4000);
        l_nota    VARCHAR2(4000);
        l_danados VARCHAR2(4000);   -- protocolo 5: unidades danadas de las contadas (vacio si no se indico)
        l_n       PLS_INTEGER;
    BEGIN
        l_ts := campo(p_raw, 3);
        IF campo(p_raw, 1) IS NULL OR campo(p_raw, 1) <> 'REC'
           OR l_ts IS NULL OR NOT REGEXP_LIKE(l_ts, '^[0-9]{1,15}$') THEN
            fallar('FORMATO_INVALIDO');
        END IF;
        l_sku    := texto(campo(p_raw, 5));
        l_cant   := texto(campo(p_raw, 6));
        l_oper   := texto(campo(p_raw, 7));
        l_nota   := texto(campo(p_raw, 8));
        l_danados := texto(campo(p_raw, 9));

        -- El conteo es unico (ACTUAL): el campo 4 del REC se acepta pero no decide el conteo.
        IF l_sku IS NULL OR LENGTH(l_sku) = 0 OR LENGTH(l_sku) > 30 THEN
            fallar('SKU_DESCONOCIDO');
        END IF;
        SELECT COUNT(*) INTO l_n FROM productos WHERE sku = l_sku;
        IF l_n = 0 THEN
            fallar('SKU_DESCONOCIDO');
        END IF;
        -- Decimal con punto, sin signo, hasta 9 enteros y 3 decimales.
        IF l_cant IS NULL OR NOT REGEXP_LIKE(l_cant, '^[0-9]{1,9}(\.[0-9]{1,3})?$') THEN
            fallar('CANTIDAD_INVALIDA');
        END IF;
        -- Danados: el mismo formato que la cantidad y nunca mas que lo contado.
        IF l_danados IS NOT NULL AND (NOT REGEXP_LIKE(l_danados, '^[0-9]{1,9}(\.[0-9]{1,3})?$')
           OR TO_NUMBER(l_danados, '999999999D999', 'NLS_NUMERIC_CHARACTERS=''.,''') > TO_NUMBER(l_cant, '999999999D999', 'NLS_NUMERIC_CHARACTERS=''.,''')) THEN
            fallar('DANADOS_INVALIDO');
        END IF;

        INSERT INTO registros_procesados
            (id_transito, id_conteo, sku, cantidad, operador, nota, fecha_captura, vigente, danados)
        VALUES
            (p_id, 'ACTUAL', l_sku,
             -- Mascara fija: no depende del NLS de la sesion.
             TO_NUMBER(l_cant, '999999999D999', 'NLS_NUMERIC_CHARACTERS=''.,'''),
             SUBSTR(l_oper, 1, 60), SUBSTR(l_nota, 1, 255),
             -- epoch_ms -> TIMESTAMP en UTC.
             TIMESTAMP '1970-01-01 00:00:00' + NUMTODSINTERVAL(TO_NUMBER(l_ts) / 1000, 'SECOND'),
             'N',
             CASE WHEN l_danados IS NULL THEN NULL ELSE TO_NUMBER(l_danados, '999999999D999', 'NLS_NUMERIC_CHARACTERS=''.,''') END);

        recalcular_vigente(l_sku);
    END procesar_fila;

    -- Conciliacion por SKU del conteo:
    --   * Entra TODO producto del catalogo. El sistema es su fila de STOCK_SISTEMA (0 si no tiene).
    --   * contada = la lectura vigente del SKU (una sola: recontar reemplaza); si no hay, NULL.
    --   * DIFERENCIA = contada - sistema (NULL sin lectura); DIFERENCIA_PCT NULL sin lectura o con sistema 0.
    PROCEDURE conciliar_interno(p_id_conteo IN VARCHAR2) IS
        l_existe PLS_INTEGER;
    BEGIN
        SELECT COUNT(*) INTO l_existe FROM conteos WHERE id_conteo = p_id_conteo;
        IF l_existe = 0 THEN
            RAISE_APPLICATION_ERROR(-20002, 'CONTEO_INEXISTENTE: ' || p_id_conteo);
        END IF;

        -- Serializa conciliaciones simultaneas (dos corridas del batch).
        LOCK TABLE conciliacion IN EXCLUSIVE MODE;

        DELETE FROM conciliacion WHERE id_conteo = p_id_conteo;

        INSERT INTO conciliacion
            (id_conteo, sku, cant_sistema, cant_contada, diferencia, diferencia_pct, fecha_calculo)
        SELECT p_id_conteo, p.sku, NVL(s.cantidad_sistema, 0), c.contada,
               CASE WHEN c.contada IS NULL THEN NULL
                    ELSE c.contada - NVL(s.cantidad_sistema, 0) END,
               CASE WHEN c.contada IS NULL OR NVL(s.cantidad_sistema, 0) = 0 THEN NULL
                    ELSE GREATEST(-99999999.99,
                         LEAST(99999999.99,
                               ROUND((c.contada - NVL(s.cantidad_sistema, 0)) / NVL(s.cantidad_sistema, 0) * 100, 2)))
               END,
               SYSTIMESTAMP
          FROM productos p
          LEFT JOIN stock_sistema s
                 ON s.id_conteo = p_id_conteo AND s.sku = p.sku
          LEFT JOIN (SELECT sku, SUM(cantidad) AS contada
                       FROM registros_procesados
                      WHERE id_conteo = p_id_conteo AND vigente = 'S'
                      GROUP BY sku) c
                 ON c.sku = p.sku;
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
            RETURN;  -- nada que hacer: no se escribe bitacora (el job corre cada intervalo)
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

        -- 5. Conciliar el conteo unico solo si entraron lecturas nuevas.
        IF l_ok > 0 THEN
            conciliar_interno('ACTUAL');
            COMMIT;
        END IF;
    END procesar_pendientes;

    PROCEDURE conciliar(p_id_conteo IN VARCHAR2 DEFAULT 'ACTUAL') IS
    BEGIN
        conciliar_interno(p_id_conteo);
        COMMIT;
    END conciliar;

    PROCEDURE reprocesar_errores(p_id_conteo IN VARCHAR2 DEFAULT NULL) IS
    BEGIN
        UPDATE captura_transito
           SET estado = 'PENDIENTE', mensaje_error = NULL, fecha_reclamo = NULL
         WHERE estado = 'ERROR'
           AND (p_id_conteo IS NULL OR p_id_conteo = 'ACTUAL');
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
                         WHERE u.uuid_dispositivo = t.uuid_dispositivo)
           -- FOTO_PROTEGIDA: la fila de una lectura con foto enlaza la evidencia (uuid, seq) con su registro.
           AND NOT EXISTS (SELECT 1 FROM fotos f
                            WHERE f.uuid_dispositivo = t.uuid_dispositivo AND f.seq = t.seq);
        COMMIT;
    END purgar_transito;

    PROCEDURE alta_sku(
        p_sku       IN VARCHAR2,
        p_nombre    IN VARCHAR2,
        p_categoria IN VARCHAR2,
        p_unidad    IN VARCHAR2 DEFAULT 'UND',
        p_costo_unit IN NUMBER  DEFAULT 0
    ) IS
        l_sku       VARCHAR2(30 CHAR)  := TRIM(p_sku);
        l_nombre    VARCHAR2(120 CHAR) := TRIM(p_nombre);
        l_categoria VARCHAR2(40 CHAR)  := TRIM(p_categoria);
        l_unidad    VARCHAR2(10 CHAR)  := NVL(TRIM(p_unidad), 'UND');
    BEGIN
        IF l_sku IS NULL OR LENGTH(l_sku) = 0 OR LENGTH(l_sku) > 30 OR INSTR(l_sku, '|') > 0
           OR INSTR(l_sku, CHR(10)) > 0 OR INSTR(l_sku, CHR(13)) > 0 THEN
            RAISE_APPLICATION_ERROR(-20010, 'SKU_INVALIDO');
        END IF;
        IF l_nombre IS NULL OR LENGTH(l_nombre) = 0 OR LENGTH(l_nombre) > 120 THEN
            RAISE_APPLICATION_ERROR(-20010, 'NOMBRE_INVALIDO');
        END IF;
        IF l_categoria IS NULL OR LENGTH(l_categoria) = 0 OR LENGTH(l_categoria) > 40 THEN
            RAISE_APPLICATION_ERROR(-20010, 'CATEGORIA_INVALIDA');
        END IF;
        IF LENGTH(l_unidad) = 0 OR LENGTH(l_unidad) > 10 THEN
            RAISE_APPLICATION_ERROR(-20010, 'UNIDAD_INVALIDA');
        END IF;

        BEGIN
            INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit)
            VALUES (l_sku, l_nombre, l_categoria, l_unidad, NVL(p_costo_unit, 0));
        EXCEPTION
            WHEN DUP_VAL_ON_INDEX THEN
                RAISE_APPLICATION_ERROR(-20011, 'SKU_YA_EXISTE');
        END;

        MERGE INTO stock_sistema s
        USING (SELECT 'ACTUAL' id_conteo, l_sku sku FROM dual) x
           ON (s.id_conteo = x.id_conteo AND s.sku = x.sku)
         WHEN MATCHED THEN UPDATE SET cantidad_sistema = 0
         WHEN NOT MATCHED THEN INSERT (id_conteo, sku, cantidad_sistema) VALUES ('ACTUAL', l_sku, 0);

        COMMIT;
    END alta_sku;

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

-- Estado inicial: el conteo ACTUAL queda conciliado (todo NULL hasta la primera lectura).
DECLARE
    l_existe PLS_INTEGER;
BEGIN
    SELECT COUNT(*) INTO l_existe FROM conteos WHERE id_conteo = 'ACTUAL';
    IF l_existe > 0 THEN
        pkg_batch.conciliar('ACTUAL');
    END IF;
END;
/
