# Inventario físico offline: APK → Bluetooth → Oracle → App de escritorio

Sistema de toma de inventario: una APK Android cuenta productos sin wifi y los envía por
Bluetooth a una app de escritorio en el PC, que los guarda en Oracle 11g, concilia contra el
stock del sistema y grafica los resultados. El plan completo está en
`docs/superpowers/plans/2026-11-09-captura-movil-bluetooth-oracle.md`.

## Requisitos del host

- Docker y Docker Compose.
- Para el Bluetooth real: BlueZ (`bluetoothd`) activo en el host y un adaptador (`hci0`).

## Puesta en marcha (estado actual: Oracle + contenedor de pruebas)

```bash
cp .env.example .env
```

```bash
docker compose up -d --wait oracle
```

La primera vez descarga la imagen y crea la base: puede tardar varios minutos.

```bash
docker compose run --rm pybase pytest server/tests -v
```

Las rutas del proyecto contienen espacios: entrecomíllalas en tus scripts.
