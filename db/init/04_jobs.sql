-- Jobs de DBMS_SCHEDULER (se crean en el esquema APP y corren como APP).
-- El intervalo del lote se configura en CONFIGURACION (clave lote.intervalo_min); el escritorio
-- reaplica el job con DBMS_SCHEDULER.SET_ATTRIBUTE ('FREQ=MINUTELY;INTERVAL=<n>').
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
SET DEFINE OFF
ALTER SESSION SET CURRENT_SCHEMA = app;

BEGIN
    -- Respaldo del disparo inmediato que hace el servicio al terminar cada sincronizacion.
    DBMS_SCHEDULER.CREATE_JOB(
        job_name        => 'APP.JOB_PROCESAR_CAPTURAS',
        job_type        => 'PLSQL_BLOCK',
        job_action      => 'BEGIN pkg_batch.procesar_pendientes(''JOB''); END;',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'FREQ=MINUTELY;INTERVAL=1',
        enabled         => TRUE,
        comments        => 'Procesa las capturas pendientes cada intervalo configurado (minutos)'
    );

    DBMS_SCHEDULER.CREATE_JOB(
        job_name        => 'APP.JOB_PURGA_TRANSITO',
        job_type        => 'PLSQL_BLOCK',
        job_action      => 'BEGIN pkg_batch.purgar_transito(7); END;',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'FREQ=DAILY',
        enabled         => TRUE,
        comments        => 'Limpia del staging lo procesado hace mas de 7 dias'
    );
END;
/
