-- Matriz de permisos del dominio final: 12 modulos por 3 roles.
-- Clave de Sincronizacion/Bluetooth: SYNC (la usa Store._operador_puede_sincronizar).
-- Niveles: NINGUNO (no ve), CONSULTA (ve), GESTION (ademas cambia datos).
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
SET DEFINE OFF
ALTER SESSION SET CURRENT_SCHEMA = app;

BEGIN
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('ADMIN', 'dashboard', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('ADMIN', 'inventario', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('ADMIN', 'graficas', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('ADMIN', 'sync', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('ADMIN', 'notificaciones', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('ADMIN', 'perfil', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('ADMIN', 'solicitudes', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('ADMIN', 'usuarios', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('ADMIN', 'permisos', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('ADMIN', 'auditoria', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('ADMIN', 'configuracion', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('ADMIN', 'respaldos', 'GESTION');

    INSERT INTO permisos (rol, modulo, nivel) VALUES ('INVENTARIO', 'dashboard', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('INVENTARIO', 'inventario', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('INVENTARIO', 'graficas', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('INVENTARIO', 'sync', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('INVENTARIO', 'notificaciones', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('INVENTARIO', 'perfil', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('INVENTARIO', 'solicitudes', 'NINGUNO');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('INVENTARIO', 'usuarios', 'NINGUNO');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('INVENTARIO', 'permisos', 'NINGUNO');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('INVENTARIO', 'auditoria', 'NINGUNO');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('INVENTARIO', 'configuracion', 'NINGUNO');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('INVENTARIO', 'respaldos', 'NINGUNO');

    INSERT INTO permisos (rol, modulo, nivel) VALUES ('OPERADOR', 'dashboard', 'NINGUNO');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('OPERADOR', 'inventario', 'NINGUNO');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('OPERADOR', 'graficas', 'NINGUNO');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('OPERADOR', 'sync', 'GESTION');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('OPERADOR', 'notificaciones', 'CONSULTA');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('OPERADOR', 'perfil', 'NINGUNO');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('OPERADOR', 'solicitudes', 'NINGUNO');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('OPERADOR', 'usuarios', 'NINGUNO');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('OPERADOR', 'permisos', 'NINGUNO');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('OPERADOR', 'auditoria', 'NINGUNO');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('OPERADOR', 'configuracion', 'NINGUNO');
    INSERT INTO permisos (rol, modulo, nivel) VALUES ('OPERADOR', 'respaldos', 'NINGUNO');
    COMMIT;
END;
/
