# Rediseño global (Motion + sistema visual) — seguimiento

Reglas fijas: identidad cromática verde (`#10B981` / `#059669` en claro), sidebar intacta, sin tocar lógica de negocio,
Bluetooth, Android ni Oracle. Toda animación pasa por `motion.animar` y respeta `APP_SIN_ANIMACIONES=1`.
Pruebas: comando docker de la memoria `ejecutar-pruebas-desktop`.

## Estado: Fases 1–7 hechas

### Fase 1 — Infraestructura global de motion
`desktop/app/views/motion_global.py`:

| Pieza | Qué hace | Dónde se activa |
|---|---|---|
| Curvas `ENTRADA` / `SALIDA` / `ASENTAR`, `resorte()` | Vocabulario de easing por intención | Todo el módulo |
| `escalonar()` | Cascada con tope | Disponible para listas |
| `cruce_tema()` | Cambio de tema con fundido, sin salto | `main.cambiar_tema` |
| `cambiar_pila()` | Cruce + deslizamiento entre formularios | `acceso.mostrar_formulario` (login / registro / olvido) |
| `aparecer_popup()` | Fundido de menús y de diálogos estándar | Todo `QMenu` y `QDialog` no translúcido (vía `vigilante`) |
| `instalar_presion()` | Feedback < 100 ms al pulsar | Todo `QPushButton`/`QToolButton` salvo la sidebar (vía `vigilante`) |
| `fundir_contenido()` | Fundido de filas cuando el modelo trae datos | Toda `QTableView` (vía `vigilante`) |

### Fase 2 — Tokens de diseño
`views/diseno.py`: radios (9/14/20), escala de espaciado (4–24), tiempos por rol (presión 90, hover 120, entrada 200,
pantalla 260, tema 240, tope 500) y parámetros de cascada. Documenta los valores que ya usa `base.py`; no cambia
ninguna medida, color ni tipografía existente (decisión: conservar la identidad). El QSS triplicado de `base.py`
**no se unificó**: hacerlo sin cambiar el aspecto exige comparación visual pantalla a pantalla con la app en pantalla.

### Fase 3 — Carga y estados
`BarridoCarga` (línea de 2 px en verde) dentro de `StateBanner`: arranca en `show_loading()` y se detiene en
`clear()`, `show_empty()` y `show_error()`. Dura lo que dura la consulta real; su animación solo corre mientras es visible.
Los estados vacíos de tablas ya existían (`vigilante._Vacio`); los errores siguen yendo a la Isla.

### Fase 4 — Pantallas
`entrada_pagina()`: al abrir una sección las tarjetas (`QFrame#card`) se revelan en cascada (32 ms entre cada una,
máx. 6 escalones) con un velo del color del lienzo que se desvanece; no mueve el layout. Se lanza desde
`main.abrir_seccion`. Cubre las ~20 vistas porque todas usan `card`. El cambio de formularios de acceso usa `cambiar_pila`.

### Fase 5 — Gráficas
Ya existían y se conservan: trazado y barras crecen de 0 a su valor real (`charts.py`, 700–750 ms), tooltips y
seguimiento en `graficas_interactivas.py`. Ninguna animación altera magnitudes finales. Sin cambios.

### Fase 6 — Isla y notificaciones
`isla.py` (1047 líneas) ya tiene cola, prioridades, pausa en hover, expansión/contracción y progreso. Sin cambios:
no se encontró un defecto que justificara tocarla.

### Fase 7 — Accesibilidad y rendimiento
- `widgets.ANIMAR` ahora también se apaga si el escritorio pide «reducir movimiento» (`gsettings enable-animations=false`);
  `APP_SIN_ANIMACIONES=0` fuerza el movimiento real, `=1` lo apaga (pruebas).
- Los temporizadores del barrido de carga solo corren visibles; los velos se destruyen al terminar (`deleteLater`).
- Feedback de presión < 100 ms; ninguna transición supera 500 ms.

## Verificación
- Suite `desktop/tests` en docker con animaciones apagadas y, para ventana/navegación/idioma/respaldos/sync, con
  animaciones reales. Los 14 fallos de la suite son preexistentes (idénticos en `main` sin estos cambios): datos de
  Oracle y un test de respaldos.
- Humo con animaciones reales: cambio de pila, presión, cruce de tema, fundido de tabla, menú, barrido, entrada de página, diálogo.

## Limitaciones
- El entorno offscreen no soporta `windowOpacity` ni mide fluidez real (60 fps); el aspecto final debe verse con pantalla.
- Reducir movimiento solo se detecta en GNOME/Cinnamon (gsettings).
- Tokens y QSS: no se rehizo la hoja de estilo (ver Fase 2).
