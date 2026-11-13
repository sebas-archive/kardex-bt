-- Matriz de permisos editable: nivel de cada rol en cada modulo (NINGUNO, CONSULTA, GESTION).
-- Los valores iniciales los pone la aplicacion de escritorio al arrancar (desktop/app/permisos.py, migrar()):
-- una sola definicion de la matriz, y una base ya creada antes de esta tabla tambien la recibe.
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
ALTER SESSION SET CURRENT_SCHEMA = APP;

CREATE TABLE permisos (
    rol     VARCHAR2(12 CHAR) NOT NULL,
    modulo  VARCHAR2(30 CHAR) NOT NULL,
    nivel   VARCHAR2(10 CHAR) NOT NULL,
    CONSTRAINT pk_permisos PRIMARY KEY (rol, modulo),
    CONSTRAINT ck_permisos_nivel CHECK (nivel IN ('NINGUNO', 'CONSULTA', 'GESTION'))
);
