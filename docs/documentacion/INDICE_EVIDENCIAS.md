# Índice de evidencias

Cada figura del documento técnico corresponde a un archivo de este directorio (`docs/documentacion/`).

| ID | Figura | Archivo | Tipo | Descripción | Criterio relacionado |
|---|---|---|---|---|---|
| E-001 | 1 | `diagramas/renderizados/02_arquitectura_general.png` | Diagrama PlantUML | Arquitectura general del sistema: capas y canales de comunicación | Arquitectura y código fuente |
| E-002 | 2 | `diagramas/renderizados/01_casos_uso.png` | Diagrama PlantUML | Diagrama de casos de uso | Funcionalidad y requisitos |
| E-003 | 3 | `diagramas/renderizados/04_despliegue.png` | Diagrama PlantUML | Diagrama de despliegue | Arquitectura y código fuente |
| E-004 | 4 | `diagramas/renderizados/03_componentes.png` | Diagrama PlantUML | Diagrama de componentes | Arquitectura y código fuente |
| E-005 | 5 | `diagramas/renderizados/07b_paquetes.png` | Diagrama PlantUML | Diagrama de paquetes y dependencias | Arquitectura y código fuente |
| E-006 | 6 | `diagramas/renderizados/07_clases_paquetes.png` | Diagrama PlantUML | Diagrama de clases de la librería btsync | Arquitectura y código fuente |
| E-007 | 7 | `capturas/codigo/codigo_01_entrada_escritorio.png` | Captura de código | Punto de entrada de la aplicación de escritorio | Arquitectura y código |
| E-008 | 8 | `capturas/codigo/codigo_02_entrada_servicio.png` | Captura de código | Punto de entrada del servicio Bluetooth | Arquitectura y código |
| E-009 | 9 | `capturas/codigo/codigo_03_configuracion_compose.png` | Captura de código | Configuración del servicio «bluetooth» en Docker Compose | Arquitectura / instalación |
| E-010 | 10 | `capturas/codigo/codigo_04_composicion_ventana.png` | Captura de código | Composición de la ventana: registro de vistas y permisos | Arquitectura y código |
| E-011 | 11 | `capturas/codigo/codigo_15_hilos_worker.png` | Captura de código | Concurrencia: QueryWorker (QRunnable) con señales Qt | Arquitectura / concurrencia |
| E-012 | 12 | `capturas/codigo/codigo_16_hilos_runner.png` | Captura de código | Concurrencia: QueryRunner entrega el resultado al hilo de la UI | Arquitectura / concurrencia |
| E-013 | 13 | `capturas/codigo/codigo_17_remoto.png` | Captura de código | Señales: ServicioRemoto convierte el estado de Oracle en señales Qt | Arquitectura / señales |
| E-014 | 14 | `capturas/codigo/codigo_13_controlador_conexion.png` | Captura de código | Controlador: una sesión por conexión y D19 (PC ocupado) | Arquitectura / concurrencia |
| E-015 | 15 | `capturas/codigo/codigo_14_servicio_tick.png` | Captura de código | Servicio: latido, pausa y estado en SERVICIO_BT | Arquitectura / concurrencia |
| E-016 | 16 | `diagramas/renderizados/09_estados.png` | Diagrama PlantUML | Máquina de estados del controlador de sincronización | Arquitectura y código fuente |
| E-017 | 17 | `capturas/codigo/codigo_11_store_conexion.png` | Captura de código | Conexión con Oracle (python-oracledb) | Conectividad / datos |
| E-018 | 18 | `diagramas/renderizados/10_modelo_datos.png` | Diagrama PlantUML | Diagrama del modelo de datos de Oracle (conteo continuo ACTUAL) | Funcionalidad / Arquitectura |
| E-019 | 19 | `capturas/codigo/codigo_22_sql_tabla_transito.png` | Captura de código | Modelo de datos: tabla de staging CAPTURA_TRANSITO | Datos |
| E-020 | 20 | `capturas/codigo/codigo_10_store_insert.png` | Captura de código | Persistencia: inserción idempotente en CAPTURA_TRANSITO | Conectividad / datos |
| E-021 | 21 | `capturas/codigo/codigo_23_sql_batch.png` | Captura de código | PKG_BATCH: validación y proceso de una lectura | Datos / funcionalidad |
| E-022 | 22 | `capturas/codigo/codigo_24_sql_permisos.png` | Captura de código | Matriz de permisos rol × módulo (Oracle) | Seguridad / datos |
| E-023 | 23 | `capturas/codigo/codigo_05_protocolo_trama.png` | Captura de código | Protocolo: construcción y validación de tramas (longitud, CRC32, formato) | Conectividad |
| E-024 | 24 | `diagramas/renderizados/05_secuencia_flujo_datos.png` | Diagrama PlantUML | Diagrama de secuencia del flujo principal de datos | Conectividad y comunicación |
| E-025 | 25 | `capturas/codigo/codigo_07_sesion_bucle.png` | Captura de código | Sesión: bucle de recepción y despacho de mensajes | Conectividad |
| E-026 | 26 | `capturas/codigo/codigo_08_sesion_rec.png` | Captura de código | Sesión: validación de secuencia, inserción y NAK (go-back-N) | Conectividad |
| E-027 | 27 | `capturas/codigo/codigo_09_sesion_ack.png` | Captura de código | Sesión: COMMIT y confirmación acumulativa ACK | Conectividad |
| E-028 | 28 | `capturas/codigo/codigo_12_bluez_perfil.png` | Captura de código | Transporte Bluetooth: perfil RFCOMM registrado por D-Bus (BlueZ ProfileManager1) | Conectividad |
| E-029 | 29 | `diagramas/renderizados/06_secuencia_comunicacion.png` | Diagrama PlantUML | Diagrama de secuencia de comunicación: corte, READY y retroceso go-back-N | Conectividad y comunicación |
| E-030 | 30 | `capturas/codigo/codigo_25_android_sync.png` | Captura de código | Android: SyncClient, protocolo de sincronización (HELLO, READY, REC, ACK) | Conectividad |
| E-031 | 31 | `capturas/codigo/codigo_26_android_runner.png` | Captura de código | Android: SyncRunner con reintentos y estados | Conectividad / UI |
| E-032 | 32 | `capturas/codigo/codigo_27_android_outbox.png` | Captura de código | Android: Outbox (Room), envío y reconciliación tras un corte | Conectividad / datos |
| E-033 | 33 | `capturas/pruebas/registro_06_comunicacion_a.png` | Registro de ejecución | Ejecución real: cuenta pendiente, aprobación y envío de 126 lecturas | Conectividad y comunicación |
| E-034 | 34 | `capturas/pruebas/registro_07_comunicacion_b.png` | Registro de ejecución | Ejecución real: estado de Oracle tras el batch | Conectividad y comunicación |
| E-035 | 35 | `capturas/pruebas/registro_08_corte.png` | Registro de ejecución | Ejecución real: corte del envío con SIGKILL y reanudación | Conectividad y comunicación |
| E-036 | 36 | `capturas/pruebas/registro_09_corte_final.png` | Registro de ejecución | Ejecución real: estado final tras la reanudación, sin duplicados | Conectividad y comunicación |
| E-037 | 37 | `diagramas/renderizados/08_actividades.png` | Diagrama PlantUML | Diagrama de actividades: de la subida al ACK y el batch PKG_BATCH.PROCESAR_PENDIENTES | Funcionalidad y requisitos |
| E-038 | 38 | `diagramas/renderizados/08b_actividad_conteo_movil.png` | Diagrama PlantUML | Diagrama de actividades del conteo en el móvil | Funcionalidad y requisitos |
| E-039 | 39 | `diagramas/renderizados/09b_estados_fila_transito.png` | Diagrama PlantUML | Estados de una fila de CAPTURA_TRANSITO | Arquitectura y código fuente |
| E-040 | 40 | `diagramas/renderizados/09c_estados_cuenta.png` | Diagrama PlantUML | Estados de una cuenta de usuario | Seguridad / Funcionalidad |
| E-041 | 41 | `capturas/aplicacion/acceso/01_acceso.png` | Captura de la aplicación | Pantalla de acceso de la aplicación de escritorio | UI/UX y Funcionalidad |
| E-042 | 42 | `capturas/codigo/codigo_18_autenticacion.png` | Captura de código | Autenticación: hash, bloqueo por intentos y auditoría | Seguridad / funcionalidad |
| E-043 | 43 | `capturas/roles/administrador/01_dashboard.png` | Captura de la aplicación | Dashboard visto por el Administrador | Funcionalidad y UI/UX |
| E-044 | 44 | `capturas/roles/administrador/02_inventario.png` | Captura de la aplicación | Módulo Inventario con datos | Funcionalidad |
| E-045 | 45 | `capturas/roles/inventario/03_graficas.png` | Captura de la aplicación | Módulo Gráficas (rol Inventario) | UI/UX y Funcionalidad |
| E-046 | 46 | `capturas/roles/administrador/08_sincronizacion.png` | Captura de la aplicación | Módulo Sincronización con el servicio en pausa | Conectividad y UI/UX |
| E-047 | 47 | `capturas/aplicacion/resoluciones/sincronizacion_1920x1080.png` | Captura de la aplicación | Sincronización a 1920 × 1080 | UI/UX y adaptabilidad |
| E-048 | 48 | `capturas/roles/administrador/03_solicitudes.png` | Captura de la aplicación | Módulo Solicitudes | Funcionalidad y Seguridad |
| E-049 | 49 | `capturas/roles/administrador/04_empleados.png` | Captura de la aplicación | Módulo Empleados | Funcionalidad y Seguridad |
| E-050 | 50 | `capturas/roles/administrador/05_roles_y_permisos.png` | Captura de la aplicación | Módulo Roles y permisos | Seguridad |
| E-051 | 51 | `capturas/roles/administrador/06_auditoria.png` | Captura de la aplicación | Módulo Auditoría | Seguridad |
| E-052 | 52 | `capturas/roles/administrador/07_configuracion.png` | Captura de la aplicación | Módulo Configuración | Funcionalidad |
| E-053 | 53 | `capturas/roles/administrador/09_respaldos.png` | Captura de la aplicación | Módulo Respaldos (estado vacío) | Funcionalidad y UI/UX (estado vacío) |
| E-054 | 54 | `capturas/aplicacion/navegacion/notificaciones_hoja.png` | Captura de la aplicación | Hoja flotante de notificaciones | UI/UX |
| E-055 | 55 | `capturas/roles/administrador/20_perfil.png` | Captura de la aplicación | Módulo Perfil | UI/UX y Seguridad |
| E-056 | 56 | `capturas/movil/movil_montaje_1_acceso.png` | Render de la APK | Pantallas de acceso y cuenta de la APK | UI/UX |
| E-057 | 57 | `capturas/movil/movil_montaje_2_captura.png` | Render de la APK | Pantallas de captura de la APK | Funcionalidad y UI/UX |
| E-058 | 58 | `capturas/movil/movil_montaje_3_sincronizacion.png` | Render de la APK | Estados de la sincronización en la APK | Conectividad y UI/UX (estados de carga y error) |
| E-059 | 59 | `capturas/movil/movil_montaje_4_apariencia.png` | Render de la APK | Notificaciones, cuenta, editor de foto y tema oscuro en la APK | UI/UX |
| E-060 | 60 | `capturas/aplicacion/pantalla_principal/dashboard_estado_de_carga.png` | Captura de la aplicación | Dashboard en estado de carga | UI/UX (estados de carga) |
| E-061 | 61 | `capturas/aplicacion/resoluciones/dashboard_900x600.png` | Captura de la aplicación | Dashboard a 900 × 600 (mínimo) | UI/UX y adaptabilidad |
| E-062 | 62 | `capturas/aplicacion/navegacion/lateral_contraida.png` | Captura de la aplicación | Barra lateral contraída a 1240 × 800 | UI/UX y adaptabilidad |
| E-063 | 63 | `capturas/aplicacion/resoluciones/inventario_1920x1080.png` | Captura de la aplicación | Inventario a 1920 × 1080 | UI/UX y adaptabilidad |
| E-064 | 64 | `capturas/aplicacion/resoluciones/sincronizacion_1366x768.png` | Captura de la aplicación | Sincronización a 1366 × 768 | UI/UX y adaptabilidad |
| E-065 | 65 | `capturas/codigo/codigo_19_hash.png` | Captura de código | Contraseñas: PBKDF2 con sal | Seguridad |
| E-066 | 66 | `capturas/codigo/codigo_20_permisos.png` | Captura de código | Permisos: matriz inicial de 12 módulos y niveles Sin acceso / Consulta / Gestión | Seguridad |
| E-067 | 67 | `capturas/codigo/codigo_21_exigir.png` | Captura de código | Permisos: revalidación en vivo antes de cambiar datos | Seguridad |
| E-068 | 68 | `capturas/roles/inventario/01_dashboard.png` | Captura de la aplicación | Experiencia del rol Inventario (cuatro secciones más Perfil) | Seguridad y UI/UX |
| E-069 | 69 | `capturas/pruebas/registro_01_servidor_limpia.png` | Registro de ejecución | Resultado de las pruebas del servidor (Oracle limpio) | Funcionalidad y Documentación |
| E-070 | 70 | `capturas/pruebas/registro_02_escritorio_limpia.png` | Registro de ejecución | Resultado de las pruebas del escritorio (Oracle limpio) | UI/UX y Funcionalidad |
| E-071 | 71 | `capturas/pruebas/registro_03_android.png` | Registro de ejecución | Resultado de las pruebas unitarias de la APK | Funcionalidad y Conectividad |
| E-072 | 72 | `capturas/pruebas/registro_04_servidor_demo.png` | Registro de ejecución | Pruebas del servidor sobre la base con datos de demostración | Funcionalidad |
| E-073 | 73 | `capturas/pruebas/registro_05_escritorio_demo.png` | Registro de ejecución | Pruebas del escritorio sobre la base con datos de demostración | Funcionalidad |
| E-074 | 74 | `capturas/pruebas/registro_10_entorno.png` | Registro de ejecución | Estado real de los contenedores y versiones del entorno | Documentación (instalación) |
| E-075 | 75 | `diagramas/renderizados/07c_clases_escritorio.png` | Diagrama PlantUML | Diagrama de clases de la aplicación de escritorio | Arquitectura y código fuente |
| E-076 | 76 | `diagramas/renderizados/07d_clases_android.png` | Diagrama PlantUML | Diagrama de clases de la APK Android (MVVM) | Arquitectura y código fuente |

## Fuentes PlantUML

- `diagramas/plantuml/01_casos_uso.puml` → `diagramas/renderizados/01_casos_uso.svg` y `.png`
- `diagramas/plantuml/02_arquitectura_general.puml` → `diagramas/renderizados/02_arquitectura_general.svg` y `.png`
- `diagramas/plantuml/03_componentes.puml` → `diagramas/renderizados/03_componentes.svg` y `.png`
- `diagramas/plantuml/04_despliegue.puml` → `diagramas/renderizados/04_despliegue.svg` y `.png`
- `diagramas/plantuml/05_secuencia_flujo_datos.puml` → `diagramas/renderizados/05_secuencia_flujo_datos.svg` y `.png`
- `diagramas/plantuml/06_secuencia_comunicacion.puml` → `diagramas/renderizados/06_secuencia_comunicacion.svg` y `.png`
- `diagramas/plantuml/07_clases_paquetes.puml` → `diagramas/renderizados/07_clases_paquetes.svg` y `.png`
- `diagramas/plantuml/07b_paquetes.puml` → `diagramas/renderizados/07b_paquetes.svg` y `.png`
- `diagramas/plantuml/07c_clases_escritorio.puml` → `diagramas/renderizados/07c_clases_escritorio.svg` y `.png`
- `diagramas/plantuml/07d_clases_android.puml` → `diagramas/renderizados/07d_clases_android.svg` y `.png`
- `diagramas/plantuml/08_actividades.puml` → `diagramas/renderizados/08_actividades.svg` y `.png`
- `diagramas/plantuml/08b_actividad_conteo_movil.puml` → `diagramas/renderizados/08b_actividad_conteo_movil.svg` y `.png`
- `diagramas/plantuml/09_estados.puml` → `diagramas/renderizados/09_estados.svg` y `.png`
- `diagramas/plantuml/09b_estados_fila_transito.puml` → `diagramas/renderizados/09b_estados_fila_transito.svg` y `.png`
- `diagramas/plantuml/09c_estados_cuenta.puml` → `diagramas/renderizados/09c_estados_cuenta.svg` y `.png`
- `diagramas/plantuml/10_modelo_datos.puml` → `diagramas/renderizados/10_modelo_datos.svg` y `.png`

## Registros de ejecución

- `anexos/registros/comunicacion_corte.txt`
- `anexos/registros/comunicacion_tcp.txt`
- `anexos/registros/entorno.txt`
- `anexos/registros/pruebas_android.txt`
- `anexos/registros/pruebas_escritorio.txt`
- `anexos/registros/pruebas_escritorio_limpia.txt`
- `anexos/registros/pruebas_fin.txt`
- `anexos/registros/pruebas_limpia_fin.txt`
- `anexos/registros/pruebas_servidor.txt`
- `anexos/registros/pruebas_servidor_limpia.txt`
