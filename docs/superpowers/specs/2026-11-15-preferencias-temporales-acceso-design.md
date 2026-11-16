# Preferencias temporales de Acceso — diseño

## Intención

Una persona que cambie tema o idioma desde la pantalla de Acceso debe conservar esa selección en toda la aplicación después de autenticarse, hasta que cambie la preferencia o cierre la aplicación.

## Objetivos

- Mantener el tema y el idioma elegidos en Acceso al entrar a la aplicación.
- No escribir esas elecciones de Acceso en Oracle ni conservarlas al reiniciar la aplicación.
- Seguir usando las preferencias guardadas de la cuenta cuando la persona no elige nada en Acceso.
- Actualizar el aspecto inmediatamente si el modo activo es `sistema` y cambia el esquema claro/oscuro del sistema operativo.

## No objetivos

- No cambiar la persistencia de preferencias desde Perfil.
- No modificar el esquema de Oracle ni los valores guardados de usuarios.

## Enfoques considerados

1. Guardar la elección de Acceso en las preferencias de la cuenta. Se descarta: convertiría una elección temporal en un cambio persistente de la cuenta.
2. Mantener una anulación temporal en Acceso durante el proceso de la aplicación. Elegido: conserva la elección tras autenticar y hasta cerrar, sin modificar Oracle.
3. Guardar la elección en `QSettings`. Se descarta: sobreviviría al cierre de la aplicación y contradice el alcance temporal solicitado.

## Diseño

`AccesoView` conservará en memoria cuáles preferencias eligió explícitamente la persona y expondrá esas anulaciones. `MainWindow.iniciar()` resolverá cada valor con la anulación temporal cuando exista; de lo contrario, usará el valor de la sesión autenticada. La sesión en memoria se actualizará con los valores resueltos para que las vistas reconstruidas mantengan el mismo estado.

`tema` instalará una única suscripción a `QStyleHints.colorSchemeChanged`. Al emitirse, volverá a aplicar la hoja de estilo y la paleta solo si el modo solicitado sigue siendo `sistema`; los modos explícitos no cambiarán.

## Verificación

- Una selección de oscuro e inglés en Acceso prevalece sobre preferencias distintas recibidas con la sesión y se refleja en la ventana principal.
- La selección de Acceso no crea claves `tema_invitado` ni `idioma_invitado` en `QSettings`.
- Un cambio de esquema simulado vuelve a aplicar el tema únicamente en modo `sistema`.
