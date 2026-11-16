"""Traducciones al inglés de los mensajes que emite la isla (la clave es el texto en español)."""

from __future__ import annotations

from .. import i18n

EN = {
    "Sesión iniciada": "Signed in",
    "Bienvenido, {nombre}": "Welcome, {nombre}",
    "Credenciales incorrectas": "Incorrect credentials",
    "Completa los campos obligatorios": "Fill in the required fields",
    "Cuenta creada correctamente": "Account created successfully",
    "No se pudo crear la cuenta": "Could not create the account",
    "Solicitud enviada": "Request sent",
    "Iniciando sesión…": "Signing in…",
    "Creando cuenta…": "Creating account…",
    "No se pudo iniciar sesión": "Could not sign in",
    "Tu cuenta todavía no puede entrar": "Your account cannot sign in yet",
    "Un administrador debe aprobarla antes de que puedas entrar.": "An administrator must approve it before you can sign in.",
    "Sesión cerrada": "Signed out",
    "Datos guardados": "Data saved",
    "No se pudo guardar": "Could not save",
    "Guardando…": "Saving…",
    "Error de conexión con Oracle": "Oracle connection error",
    "Conexión con Oracle restablecida": "Oracle connection restored",
    "Bluetooth: celular conectado": "Bluetooth: phone connected",
    "Bluetooth desconectado": "Bluetooth disconnected",
    "Sincronizando inventario…": "Syncing inventory…",
    "Sincronización completada": "Sync completed",
    "Error al sincronizar": "Sync error",
    "Inventario actualizado": "Inventory updated",
    "Creando respaldo…": "Creating backup…",
    "Respaldo creado": "Backup created",
    "Error al crear el respaldo": "Could not create the backup",
    "Restaurando respaldo…": "Restoring backup…",
    "Error al restaurar el respaldo": "Could not restore the backup",
    "Respaldo automático guardado": "Automatic backup saved",
    "Inventario exportado": "Inventory exported",
    "No se pudo exportar": "Could not export",
    "Cambios guardados": "Changes saved",
    "Rol actualizado": "Role updated",
    "Contraseña restablecida": "Password reset",
    "Solicitud resuelta": "Request resolved",
    "Perfil actualizado": "Profile updated",
    "Foto actualizada": "Photo updated",
    "Foto eliminada": "Photo removed",
    "No se pudo completar la operación": "The operation could not be completed",
    "Operación completada": "Operation completed",
    "Notificaciones marcadas como leídas": "Notifications marked as read",
    "Servicio Bluetooth pausado": "Bluetooth service paused",
    "Servicio Bluetooth reanudado": "Bluetooth service resumed",
}


def registrar() -> None:
    i18n.registrar(EN)
