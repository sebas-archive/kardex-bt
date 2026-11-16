# Preferencias temporales de Acceso Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Conservar durante la ejecución el tema e idioma elegidos en Acceso y actualizar el modo Sistema cuando cambie el sistema operativo.

**Architecture:** `AccesoView` conservará anulaciones temporales sin usar `QSettings`; `MainWindow` las resolverá al recibir una sesión. El módulo `tema` observará el cambio de esquema del sistema y reaplicará sus recursos únicamente para el modo `sistema`.

**Tech Stack:** Python 3.12, PyQt6, pytest, pytest-qt.

**Spec:** `docs/superpowers/specs/2026-11-15-preferencias-temporales-acceso-design.md`

## Global Constraints

- Las preferencias elegidas en Acceso son solo de la ejecución actual y no se escriben en Oracle ni en `QSettings`.
- Si Acceso no recibió una elección explícita, se aplican las preferencias de la sesión autenticada.
- El modo `sistema` responde a cambios de esquema; `claro` y `oscuro` no.

## Review Focus

- Seleccionar tema e idioma antes de entrar no debe ser reemplazado por una sesión con valores distintos.
- Una sesión sin selección previa debe conservar sus preferencias almacenadas.
- El modo explícito no debe cambiar cuando se notifique un cambio del sistema.
- Las conexiones repetidas al observador del sistema no deben provocar reaplicaciones duplicadas.
- El cierre de sesión debe seguir mostrando la preferencia temporal activa.

### Task 1: Resolver preferencias temporales al iniciar sesión

**Files:**
- Modify: `desktop/app/views/acceso.py`
- Modify: `desktop/app/main.py`
- Test: `desktop/tests/test_app.py`

**Interfaces:**
- Produces: `AccesoView.preferencias_temporales() -> tuple[str | None, str | None]`.
- Consumes: `MainWindow.iniciar(sesion: auth.Sesion) -> None`.

- [ ] **Step 1: Write the failing test**

```python
def test_access_preferences_override_account_preferences_for_this_app_run(qtbot, puente):
    ventana = build_window(puente, auto_refresh_ms=0)
    ventana.acceso._elegir_tema_invitado("oscuro")
    ventana.acceso._elegir_idioma_invitado("en")
    ventana.iniciar(Sesion("ana", "Ana", ADMIN, tema="claro", idioma="es"))
    assert (tema.modo(), i18n.idioma()) == ("oscuro", "en")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests/test_app.py::test_access_preferences_override_account_preferences_for_this_app_run -q`

Expected: FAIL because `iniciar()` replaces the Access selection with the account preferences.

- [ ] **Step 3: Implement the temporary-preference interface**

Remove the guest theme and language reads/writes from `QSettings`; retain `QSettings` only for the remembered username. Return explicit temporary overrides from `AccesoView`, resolve them first in `MainWindow.iniciar()`, and store resolved values in the in-memory session without invoking `auth.guardar_preferencias`.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests/test_app.py -q`

Expected: PASS.

### Task 2: React to system scheme changes

**Files:**
- Modify: `desktop/app/tema.py`
- Test: `desktop/tests/test_app.py`

**Interfaces:**
- Produces: one internal `QStyleHints.colorSchemeChanged` listener per `QApplication`.
- Consumes: `tema.aplicar(app, modo_pedido)`.

- [ ] **Step 1: Write the failing test**

```python
def test_system_theme_reapplies_when_the_system_scheme_changes(qapp, monkeypatch):
    tema.aplicar(qapp, "sistema")
    # Simulate a system-scheme signal after the resolver changes to dark.
    ...
    assert qapp.styleSheet() == estilo()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests/test_app.py::test_system_theme_reapplies_when_the_system_scheme_changes -q`

Expected: FAIL because `tema` currently evaluates the system scheme only when `aplicar()` is called.

- [ ] **Step 3: Implement the single observer in `tema.py`**

Keep the observed application and its style hints module-local. Connect `colorSchemeChanged` once, and have its callback call `aplicar()` only while `modo()` is `sistema`.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests/test_app.py -q`

Expected: PASS.

- [ ] **Step 5: Run the full desktop suite**

Run: `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests -q`

Expected: PASS.
