# Fase 3b: movimientos (entradas y salidas) y ajustes. Plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: superpowers:executing-plans (el usuario eligió Native en la Fase 1). Pasos con casillas (`- [ ]`).

**Meta:**
- Inventario registra entradas y salidas, que cambian la existencia al momento, y las consulta en un historial único («Movimientos»).
- Inventario solicita ajustes de existencia, a mano o desde una diferencia. Los críticos esperan la aprobación del Administrador.

**Arquitectura:**
- Una sola tabla, `movimientos` (`movimientos_tst` en las pruebas), guarda entradas, salidas y ajustes.
- Cada movimiento aplicado actualiza `existencias` en la misma transacción. La fila de la existencia se bloquea con `SELECT … FOR UPDATE`.
- El módulo nuevo es `desktop/app/movimientos.py`. Sigue el patrón de `maestros.py`: constantes de tabla cambiables en las pruebas, `migrar()` idempotente con `db.ddl_tolerante`, y errores para la persona como `ErrorDeAcceso`.

**Stack:** Python 3.12, PyQt6, python-oracledb, Oracle XE 11g.

**Spec:** la especificación del usuario, rol Inventario:
- §6 Registro de entradas: producto, cantidad, almacén, fecha, observaciones e historial.
- §7 Registro de salidas: producto, cantidad, almacén, motivo, observaciones e historial.
- §8 Movimientos: consultar entradas, salidas y ajustes; filtrar por producto, fecha y responsable.
- §9 Ajustes: consultar las diferencias reportadas; solicitar y registrar ajustes con motivo; historial; los ajustes críticos requieren aprobación del Administrador.
- §10 Diferencias: «gestionar la corrección correspondiente».

Matriz de permisos: Entradas y salidas (Admin Consulta, Inventario Gestiona); Movimientos (Admin Consulta, Inventario Gestiona); Ajustes (Admin «Aprueba críticos», Inventario Gestiona). El boceto se aprobó el 2026-11-13.

## Decisiones acordadas
- **Dos pantallas.** «Movimientos» reúne entradas, salidas e historial, con «+ Entrada…» y «− Salida…». La otra es «Ajustes».
- **Ajuste crítico:** el cambio es de **10 % o más** de la existencia anterior (si la anterior es 0, cualquier cambio cuenta), **o** la diferencia vale **$200.000 o más** (`|Δ| × costo_unit`). Es un valor fijo; en la Fase 5 pasa a Configuración.
- **Ajuste crítico pendiente:** no toca la existencia hasta que se aprueba. Rechazarlo exige motivo.
- **Diferencias:** tiene un botón nuevo, «Ajustar existencia…», y la diferencia ajustada se muestra como «Ajustada», o «Ajuste pendiente» si el ajuste espera aprobación.

## Restricciones globales
- **Tipos:** `ENTRADA`, `SALIDA` y `AJUSTE`. **Estados:** `APLICADO`, `PENDIENTE` y `RECHAZADO`; en pantalla, «Aplicado», «Pendiente de aprobación» y «Rechazado».
- **Motivos de salida:** «Venta», «Consumo interno», «Daño», «Vencimiento» y «Otro».
- **Cantidades:** mayores que 0 (en un ajuste, la cantidad nueva puede ser 0), como máximo 999 999 999,999 y con hasta 3 decimales.
- **Existencias:** nunca quedan por debajo de 0. Una salida mayor que lo que hay se rechaza: «Solo hay N en ese almacén.»
- **Fecha de entrada o salida:** hoy por defecto. Puede ser anterior, nunca futura.
- **Qué se ofrece al registrar:** solo almacenes activos y productos de categorías activas (como en las tareas).
- **Permisos:**
  - Registrar una entrada o una salida exige `GESTION` en `entradas_salidas`.
  - Ver «Movimientos» exige `CONSULTA` en `movimientos`.
  - Solicitar un ajuste exige `GESTION` en `ajustes` y un rol que **no** sea ADMIN. La especificación dice que el Administrador nunca edita la operación diaria; además, así nadie aprueba su propio ajuste.
  - Aprobar o rechazar exige `GESTION` en `ajustes` y rol `ADMIN`, comprobado en vivo.
  - `entradas_salidas`, `movimientos` y `ajustes` entran en `permisos.EN_USO`.
- **Un ajuste se aplica como delta.** Al solicitarlo se guardan `antes` (la existencia de ese momento) y `despues` (la cantidad pedida). Al aprobarlo se suma `Δ = despues − antes` a la existencia de ese momento. Así, los movimientos que ocurran mientras tanto no se pierden. Si el resultado fuera negativo, la aprobación se rechaza con un mensaje.
- **Ajuste desde una diferencia:** la cantidad propuesta es la existencia actual del almacén de la tarea más la diferencia del conteo (`contado − sistema`), sin bajar de 0. La persona puede cambiarla.
- Toda consulta a Oracle va fuera del hilo de la interfaz. Sin commits hasta que el usuario los pida.
- **Comandos:** escritorio, `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests -q`.

## Review Focus
1. **Dos usuarios dan salida al mismo producto a la vez:** no puede quedar negativo ni perderse una de las dos (bloqueo de la fila).
2. **Se aprueba un ajuste después de que hubo movimientos:** se aplica el delta sobre lo que hay ahora, no se pisa con el «después» viejo.
3. **Entrada de un producto que no tenía fila en ese almacén:** se crea la fila; con dos a la vez no sale ORA-00001.
4. **Ajuste pendiente que otro ya resolvió, o que ya no existe:** sale un mensaje («ya fue resuelto»), no se aplica dos veces.
5. **Un Administrador degradado** a Inventario a mitad de sesión ya no puede aprobar (comprobación en vivo).

---

### Task 1: `movimientos.py`, el modelo
**Archivos:**
- Crear: `desktop/app/movimientos.py`.
- Modificar: `desktop/app/permisos.py` (`EN_USO`), `desktop/app/main.py` (`movimientos.migrar()`) y `desktop/app/tareas.py`:
  - `listar_diferencias` muestra `AJUSTADA` o `AJUSTE_PENDIENTE` si hay un ajuste no rechazado con ese `id_conteo` y SKU;
  - `NOMBRE_REVISION` gana «Ajustada» y «Ajuste pendiente»;
  - `marcar_revisada` y `pedir_recuento` siguen igual.
- Pruebas: `desktop/tests/test_movimientos.py`, con una fixture `movimientos_db` en `conftest.py` sobre `tareas_db` que apunta `TABLA` a `movimientos_tst` y la vacía.

**Produce:**
- Constantes: `TABLA`, `ENTRADA`, `SALIDA`, `AJUSTE`, `APLICADO`, `PENDIENTE`, `RECHAZADO`, `NOMBRE_TIPO`, `NOMBRE_ESTADO`, `MOTIVOS_SALIDA`, `UMBRAL_PCT = 10` y `UMBRAL_VALOR = 200_000`.
- `@dataclass(frozen=True) Movimiento(id, fecha, tipo, sku, producto, almacen, nombre_almacen, cantidad, antes, despues, motivo, observaciones, responsable, estado, resuelto_por, motivo_rechazo, id_conteo)`:
  - `cantidad` es el delta con signo;
  - `antes` y `despues` son `float | None`.
- `es_critico(antes: float, despues: float, costo_unit: float) -> bool` (función pura).
- `listar() -> list[Movimiento]`: del más reciente al más antiguo.
- `registrar_entrada(quien, sku, almacen, cantidad: float, fecha: date, observaciones: str) -> int`
- `registrar_salida(quien, sku, almacen, cantidad: float, fecha: date, motivo: str, observaciones: str) -> int`
- `existencia(sku, almacen) -> float`: 0 si no hay fila.
- `propuesta_desde_diferencia(id_conteo, sku) -> tuple[str, float, float]`: (almacén, actual, propuesta).
- `solicitar_ajuste(quien, sku, almacen, nueva: float, motivo: str, id_conteo: str | None = None) -> str`: devuelve `APLICADO` o `PENDIENTE`.
- `aprobar(quien, id_mov) -> None` y `rechazar(quien, id_mov, motivo) -> None`.
- `migrar() -> None`: crea la secuencia `seq_movimientos` y la tabla:
  - columnas: `id`, `tipo`, `sku`, `almacen`, `cantidad NUMBER(12,3)`, `antes`, `despues`, `fecha TIMESTAMP`, `registrado TIMESTAMP DEFAULT SYSTIMESTAMP`, `motivo VARCHAR2(60)`, `observaciones VARCHAR2(300)`, `responsable VARCHAR2(30)`, `estado`, `resuelto_por`, `resuelto`, `motivo_rechazo VARCHAR2(300)`, `id_conteo VARCHAR2(30)`;
  - CHECKs sobre tipo y estado;
  - sin FK hacia tablas `*_tst`.

- [ ] **Pruebas RED:**
  - `es_critico` en sus límites: 10 % exacto, menos de 10 %, antes 0, valor 200 000 exacto y valor por debajo;
  - una entrada suma, y crea la fila si no existía;
  - una salida resta, se rechaza si supera lo que hay, y exige motivo;
  - fecha futura rechazada; cantidad 0 o negativa rechazada; más de 3 decimales rechazada;
  - almacén inactivo rechazado;
  - el Administrador no registra entradas ni salidas;
  - ajuste no crítico → `APLICADO` y la existencia cambia;
  - ajuste crítico → `PENDIENTE` y la existencia no cambia hasta aprobar;
  - aprobar aplica el delta sobre la existencia actual (Review Focus 2);
  - aprobar dos veces → «ya fue resuelto» (Review Focus 4);
  - rechazar exige motivo;
  - Inventario no aprueba; el Administrador no solicita;
  - un Administrador degradado no aprueba (Review Focus 5);
  - `propuesta_desde_diferencia` = actual + diferencia;
  - la diferencia ajustada aparece como «Ajustada» (o «Ajuste pendiente»);
  - dos salidas simultáneas desde dos hilos nunca dejan la existencia negativa (Review Focus 1).
- [ ] Implementar y dejar GREEN; correr la suite del escritorio.

### Task 2: pantallas Movimientos y Ajustes, y el botón en Diferencias
**Archivos:**
- Crear: `desktop/app/views/movimientos.py` (`MovimientosView`, `pedir_movimiento`) y `desktop/app/views/ajustes.py` (`AjustesView`, `pedir_ajuste`).
- Modificar: `desktop/app/views/diferencias.py` (botón `btn_ajustar` «Ajustar existencia…»), `main.py` (secciones «Movimientos», módulo `movimientos`, y «Ajustes», módulo `ajustes`, detrás de «Diferencias») y `views/iconos.py`.
- Pruebas: `desktop/tests/test_movimientos_views.py`.

**Sigue el patrón de** las vistas de la Fase 3: `QueryRunner`, `StateBanner` para «sin datos» o «sin coincidencias», `lbl_error` para los errores de una acción (el refresco no los borra) y la fila elegida conservada.

**Produce:**
- `pedir_movimiento(padre, tipo, almacenes, productos, inicial=None, error="") -> tuple[sku, almacen, cantidad: float, fecha: date, motivo: str, observaciones] | None`:
  - en una entrada, el motivo es `""`;
  - valida en el diálogo antes de cerrarlo;
  - si el PC rechaza, se reabre con lo escrito.
- `MovimientosView`:
  - expone `filas()`, `btn_entrada`, `btn_salida`, `combo_tipo`, `combo_almacen`, `combo_responsable`, `fecha_desde`, `fecha_hasta` y `txt_buscar`;
  - columnas: Fecha, Tipo, Producto, Almacén, Cantidad («+50», «−3»), Motivo / observación, Responsable y Estado;
  - los ajustes rechazados se ven en gris.
- `pedir_ajuste(padre, almacenes, productos, inicial=None, error="") -> tuple[sku, almacen, nueva: float, motivo] | None`:
  - con `inicial=(sku, almacen, propuesta, motivo)`, los campos de producto y almacén quedan fijos;
  - muestra la existencia actual (se pasa en `inicial`) y avisa «Este ajuste necesitará aprobación del Administrador» cuando `es_critico`.
- `AjustesView`:
  - expone `filas()`, `combo_estado`, `btn_nuevo` (Inventario), `btn_aprobar` y `btn_rechazar` (Administrador; habilitados solo en `PENDIENTE`);
  - columnas: Fecha, Producto, Almacén, Antes, Después, Dif., Motivo, Estado y Solicitó;
  - «Rechazar» pide el motivo con `pedir_texto`.
- `DiferenciasView.btn_ajustar`:
  - visible para quien tiene `GESTION` en `ajustes` y no es ADMIN;
  - habilitado para una diferencia que no esté ya ajustada o pendiente;
  - abre `pedir_ajuste` con la propuesta.

- [ ] **Pruebas RED:**
  - registrar una entrada y una salida con el diálogo sustituido: aparecen en la tabla y la existencia cambia;
  - filtros por tipo, almacén, responsable, fechas y texto;
  - una salida mayor que lo que hay se reabre con el error;
  - el Administrador ve Movimientos sin botones;
  - un ajuste crítico pendiente → el Administrador lo aprueba en Ajustes y pasa a «Aplicado»; rechazar con motivo → «Rechazado»;
  - Inventario no ve Aprobar ni Rechazar;
  - «Ajustar existencia…» desde Diferencias deja la diferencia «Ajustada»;
  - las secciones según los permisos.
- [ ] Implementar y dejar GREEN; correr la suite completa del escritorio; sacar las capturas offscreen y revisarlas.

### Task 3: documentación
- [ ] En `docs/arquitectura.md`, la decisión D29 y la sección 6.
- [ ] El README.
- [ ] El UML 04 (tabla `movimientos`); regenerar sus SVG y pasar `test_uml`.
