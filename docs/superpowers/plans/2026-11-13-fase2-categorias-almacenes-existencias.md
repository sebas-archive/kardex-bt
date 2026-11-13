# Fase 2: categorías, almacenes y existencias — Plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: superpowers:executing-plans (el usuario eligió Native en la Fase 1). Pasos con casillas (`- [ ]`).

**Meta:** Tres pantallas nuevas en el escritorio: Categorías y Almacenes (crear, editar, activar/desactivar) y Existencias (consulta por producto × almacén con búsqueda y filtros), sobre tablas nuevas en Oracle.

**Arquitectura:** Tablas `categorias`, `almacenes` y `existencias`, y la columna `productos.stock_minimo`, creadas y sembradas por `desktop/app/maestros.py::migrar()` al arrancar, igual que `auth.migrar()`. Las escrituras pasan por `permisos.exigir(quien, "categorias")`. Las vistas siguen el patrón de `views/usuarios.py` (`QueryRunner`, `StateBanner`, filtrado en memoria).

**Stack:** Python 3.12, PyQt6, python-oracledb, Oracle XE 11g.

**Spec:** especificación pegada por el usuario (secciones «Gestión de categorías y almacenes» y «Consulta de existencias» del rol Inventario) más el boceto aprobado el 2026-11-13.

## Decisiones acordadas
- Boceto aprobado: Categorías (nombre, productos, estado), Almacenes (código, nombre, ubicación, estado) y Existencias (código, producto, categoría, almacén, cantidad, estado), con filtros por almacén, categoría y estado.
- Las existencias viven en una tabla nueva (producto × almacén), sembrada con los datos de ejemplo. Los conteos no cambian en esta fase.
- Desactivar no borra nada.
- El móvil queda para la Fase 3.

## Restricciones globales
- Estado de una existencia: `AGOTADO` si la cantidad es 0; `STOCK_BAJO` si está por debajo de `productos.stock_minimo`; si no, `DISPONIBLE`. En pantalla: «Agotado», «Stock bajo», «Disponible».
- Permisos: escribir categorías o almacenes exige `GESTION` en `categorias`; ver Existencias exige `CONSULTA` en `existencias`. `categorias` pasa a `permisos.EN_USO`, igual que `conteos`, que pasa a controlar la sección «Inventario» (conciliación de conteos).
- Toda consulta a Oracle fuera del hilo de la interfaz; las pruebas usan tablas `*_tst`.
- Sin commits hasta que el usuario los pida.
- Comandos de prueba: `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests -v`.

## Review Focus
1. Renombrar una categoría actualiza los productos que la usan, sin dejarlos huérfanos; un nombre repetido (sin distinguir mayúsculas) se rechaza.
2. Un código de almacén repetido o vacío se rechaza con un mensaje, no con un ORA-00001.
3. `migrar()` es idempotente y no pisa lo que el usuario ya editó.
4. Un producto sin fila de existencias en un almacén no aparece en ese almacén (no se inventa un 0).
5. Inventario (rol sin `GESTION` en `categorias`) no puede escribir, aunque llame a la función directamente.

---

### Tarea 1: `maestros.py`, el modelo y la migración
**Archivos:** crear `desktop/app/maestros.py` y `db/init/07_maestros.sql` (solo DDL); modificar `desktop/app/permisos.py` (`EN_USO`) y `desktop/app/main.py` (`maestros.migrar()`); pruebas en `desktop/tests/test_maestros.py` y en la fixture `maestros_db` de `conftest.py`.

**Produce:**
- `@dataclass Categoria(nombre: str, activa: bool, productos: int)`
- `@dataclass Almacen(codigo: str, nombre: str, ubicacion: str, activo: bool)`
- `@dataclass Existencia(sku, producto, categoria, codigo_almacen, almacen, cantidad: float, minimo: float, estado: str)`
- `listar_categorias() -> list[Categoria]`, `crear_categoria(quien, nombre)`, `renombrar_categoria(quien, actual, nuevo)`, `activar_categoria(quien, nombre, activa: bool)`
- `listar_almacenes() -> list[Almacen]`, `crear_almacen(quien, codigo, nombre, ubicacion)`, `editar_almacen(quien, codigo, nombre, ubicacion)`, `activar_almacen(quien, codigo, activo: bool)`
- `listar_existencias() -> list[Existencia]`
- `migrar() -> None`. Siembra, solo en tablas vacías:
  - las categorías, desde los valores distintos de `productos.categoria`;
  - los almacenes `ALM-01 Bodega Norte` y `ALM-02 Bodega Sur`;
  - las existencias en `ALM-01`, con el `stock_sistema` del conteo más reciente (0 si no hay);
  - `stock_minimo` = 10.
- Constantes `CATEGORIAS`, `ALMACENES`, `EXISTENCIAS` (nombres de tabla, cambiables en las pruebas). Los errores para la persona se lanzan como `auth.ErrorDeAcceso`.

- [ ] Pruebas RED: siembra e idempotencia; crear, renombrar (los productos siguen en la categoría nueva) y duplicar categoría; crear, editar, duplicar y dejar vacío un almacén; activar y desactivar; estado de una existencia (0 → AGOTADO; por debajo del mínimo → STOCK_BAJO); Inventario no escribe.
- [ ] Implementar y dejar GREEN.

### Tarea 2: vistas y cableado
**Archivos:** crear `views/maestros.py` (con `CategoriasView` y `AlmacenesView`) y `views/existencias.py` (`ExistenciasView`); modificar `main.py` (secciones «Categorías» y «Almacenes» con módulo `categorias`, «Existencias» con `existencias`, «Inventario» pasa a `conteos`) y `views/iconos.py`; pruebas en `test_maestros_views.py`.

**Produce:**
- `pedir_texto` y `pedir_almacen(padre, inicial) -> tuple[str, str, str] | None` como funciones del módulo, para poder sustituirlas en las pruebas.
- Las vistas exponen `filas()`, `seleccionar(...)`, los botones `btn_nuevo`, `btn_editar` y `btn_estado`, y los filtros.
- [ ] Pruebas RED:
  - la tabla muestra los datos;
  - crear con el diálogo sustituido;
  - desactivar y activar;
  - los filtros de Existencias (almacén, categoría, estado y texto);
  - Inventario ve Categorías con los botones activos y el Administrador sin ellos;
  - un rol sin `existencias` no ve la sección.
- [ ] Implementar y dejar GREEN; correr la suite completa del escritorio; revisar las capturas.

### Tarea 3: documentación
- [ ] `docs/arquitectura.md` (nueva decisión D27 y la sección 6), README y el UML 04 (modelo de datos), regenerando sus SVG.
