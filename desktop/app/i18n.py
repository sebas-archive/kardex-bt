"""Traducciones de la interfaz: el texto en español es la clave y el inglés es el destino.

La aplicación se escribe en español; cada texto visible pasa por ``t()``. Si el idioma activo es ``en`` se busca
la clave en el diccionario; si falta, se devuelve el español (nunca se rompe la pantalla por una traducción).
El idioma se guarda por usuario en Oracle y ``main.py`` lo fija al abrir la sesión.

``registrar()`` permite que otros módulos aporten sus propias traducciones sin editar este archivo.
"""

from __future__ import annotations

from typing import Any

IDIOMAS = ("es", "en")
NOMBRE_IDIOMA = {"es": "Español", "en": "English"}

_IDIOMA = "es"

_EN: dict[str, str] = {
    # ------------------------------------------------ navegación y roles
    "Dashboard": "Dashboard",
    "Inventario": "Inventory",
    "Gráficas": "Charts",
    "Sincronización": "Synchronization",
    "Notificaciones": "Notifications",
    "Perfil": "Profile",
    "Solicitudes": "Requests",
    "Empleados": "Employees",
    "Roles y permisos": "Roles and permissions",
    "Auditoría": "Audit log",
    "Configuración": "Settings",
    "Respaldos": "Backups",
    "Administrador": "Administrator",
    "Inventario (rol)": "Inventory",
    "Operador de Inventario": "Inventory Operator",
    "Sin rol": "No role",
    "Activa": "Active",
    "Suspendida": "Suspended",
    "Pendiente": "Pending",
    "Rechazada": "Rejected",
    "Activo": "Active",
    "Suspendido": "Suspended",
    # ------------------------------------------------ acceso
    "Kardex — Gestión de inventario": "Kardex — Inventory management",
    "Conteo físico con el celular, sin red.\nLos datos llegan por Bluetooth y Oracle los concilia.":
        "Physical counting with the phone, offline.\nData arrives over Bluetooth and Oracle reconciles it.",
    "Iniciar sesión": "Sign in",
    "Entra con tu cuenta del PC.": "Sign in with your PC account.",
    "Usuario": "Username",
    "Contraseña": "Password",
    "Entrar": "Sign in",
    "Crear cuenta": "Create account",
    "¿Olvidaste tu contraseña?": "Forgot your password?",
    "¿No tienes cuenta?": "Don't have an account?",
    "¿Ya tienes cuenta?": "Already have an account?",
    "La primera cuenta queda como administrador; las demás esperan a que un administrador les asigne el rol.":
        "The first account becomes the administrator; the rest wait for an administrator to assign a role.",
    "Nombre completo": "Full name",
    "Usuario (3 a 30: letras, números, punto o guion)": "Username (3 to 30: letters, numbers, dot or dash)",
    "Correo electrónico": "Email address",
    "Repite la contraseña": "Repeat password",
    "Mínimo 8 caracteres, con letras y números": "At least 8 characters, with letters and numbers",
    "Débil": "Weak",
    "Aceptable": "Fair",
    "Buena": "Good",
    "Fuerte": "Strong",
    "Contraseña nueva": "New password",
    "Repite la contraseña nueva": "Repeat the new password",
    "Enviar solicitud": "Send request",
    "Escribe la que quieres usar. Un administrador la aprueba y desde entonces entras con ella.":
        "Write the password you want. An administrator approves it and from then on you sign in with it.",
    "¿Ya la recuerdas?": "Remembered it?",
    "Pregunta de seguridad": "Security question",
    "Respuesta de seguridad": "Security answer",
    "Ver pregunta": "Show question",
    "Elige una pregunta…": "Choose a question…",
    "Solo el Administrador usa pregunta de seguridad. Si eres Inventario, la solicitud va a aprobación.":
        "Only the Administrator uses a security question. If you are Inventory, the request goes to approval.",
    "Usuario o contraseña incorrectos.": "Incorrect username or password.",
    "Demasiados intentos. Espera {segundos} segundos y vuelve a probar.":
        "Too many attempts. Wait {segundos} seconds and try again.",
    "Ese usuario ya existe.": "That username already exists.",
    "Ese correo ya está en uso.": "That email is already in use.",
    "El correo no es válido.": "That email address is not valid.",
    "Los operadores usan la app móvil.": "Operators use the mobile app.",
    "Cuenta en estado {estado}.": "Account is {estado}.",
    "No se pudo consultar la base de datos: {mensaje}": "Could not reach the database: {mensaje}",
    "Sin datos": "No data",
    "Cargando…": "Loading…",
    "Reintentar": "Retry",
    # ------------------------------------------------ estado de cuenta
    "Tu cuenta no puede entrar todavía": "Your account cannot sign in yet",
    "Estado de la cuenta": "Account status",
    "Motivo": "Reason",
    "Fecha de registro": "Registration date",
    "Comprobar estado": "Check status",
    "Volver al acceso": "Back to sign-in",
    "Comprobando…": "Checking…",
    # ------------------------------------------------ solicitudes
    "Solicitudes pendientes": "Pending requests",
    "Cuentas nuevas": "New accounts",
    "Contraseñas por aprobar": "Passwords awaiting approval",
    "Historial": "History",
    "Rol:": "Role:",
    "Aprobar": "Approve",
    "Rechazar…": "Reject…",
    "Aprobar contraseña": "Approve password",
    "Rechazar": "Reject",
    "Origen": "Source",
    "Registro": "Registered",
    "Resultado": "Result",
    "Por": "By",
    "PC": "PC",
    "Celular": "Phone",
    "Aprobada": "Approved",
    "Rechazada (solicitud)": "Rejected",
    "Rechazar cuenta": "Reject account",
    "¿Por qué rechazas la cuenta de {nombre}? (lo verá al intentar entrar)":
        "Why are you rejecting {nombre}'s account? (they will see it when signing in)",
    "¿Por qué rechazas la solicitud de contraseña de {nombre}? (lo verá al entrar)":
        "Why are you rejecting {nombre}'s password request? (they will see it when signing in)",
    "Escribe el motivo.": "Write the reason.",
    "El motivo puede tener máximo 300 caracteres.": "The reason can be at most 300 characters.",
    "Esta solicitud ya fue resuelta.": "This request was already resolved.",
    "Aprobar seleccionadas": "Approve selected",
    "Rechazar seleccionadas": "Reject selected",
    "Aprobar contraseñas": "Approve passwords",
    "Rechazar contraseñas": "Reject passwords",
    "Se aprobarán {n} solicitudes de contraseña.": "{n} password requests will be approved.",
    "Se rechazarán {n} solicitudes de contraseña.": "{n} password requests will be rejected.",
    "La cuenta del móvil solo puede aprobarse como Operador de Inventario.":
        "A phone account can only be approved as Inventory Operator.",
    "Una cuenta del PC solo puede ser de Inventario.": "A PC account can only have the Inventory role.",
    "Solo existe un Administrador y no se puede crear otro.": "There is only one Administrator and no other can be created.",
    # ------------------------------------------------ empleados
    "Las personas con cuenta aprobada. Aquí se cambia el rol, se suspende una cuenta (con motivo) o se reactiva, y se pone una contraseña nueva. Las cuentas nuevas se aprueban en «Solicitudes».":
        "People with an approved account. Change the role, suspend an account (with a reason) or reactivate it, and set a new password. New accounts are approved in Requests.",
    "Buscar por nombre, usuario o correo": "Search by name, username or email",
    "Todos los roles": "All roles",
    "Todos los estados": "All states",
    "Correo": "Email",
    "Nombre": "Name",
    "Rol": "Role",
    "Estado": "Status",
    "Cambiar rol": "Change role",
    "Suspender": "Suspend",
    "Reactivar": "Reactivate",
    "Poner contraseña nueva…": "Set new password…",
    "Desvincular teléfono": "Unlink phone",
    "La cuenta del celular queda libre para el próximo teléfono que sincronice con ella.":
        "The phone account becomes free for the next phone that synchronizes with it.",
    "Contraseña nueva para {nombre} (mínimo 8, con letras y números):":
        "New password for {nombre} (at least 8 characters, with letters and numbers):",
    "Sin empleados todavía": "No employees yet",
    "Ningún empleado coincide con el filtro": "No employee matches the filter",
    "El Administrador no cambia de rol ni se suspende.": "The Administrator does not change role or get suspended.",
    "La contraseña de un operador vive en el teléfono.": "An operator's password lives on the phone.",
    # ------------------------------------------------ roles y permisos
    "Roles y permisos por módulo": "Roles and permissions by module",
    "Sin acceso": "No access",
    "Consulta": "View",
    "Gestión": "Manage",
    "Módulo": "Module",
    "La fila del Administrador está bloqueada: siempre tiene Gestión.":
        "The Administrator row is locked: it always has Manage.",
    "No se pudo guardar el cambio. Se volvió a leer la matriz.":
        "The change could not be saved. The matrix was reloaded.",
    "Permiso actualizado.": "Permission updated.",
    # ------------------------------------------------ perfil
    "Tu cuenta": "Your account",
    "Cambiar contraseña": "Change password",
    "Contraseña actual": "Current password",
    "Contraseña nueva (mínimo 8, con letras y números)": "New password (at least 8 characters, with letters and numbers)",
    "Repite la contraseña nueva": "Repeat the new password",
    "Contraseña cambiada.": "Password changed.",
    "Solicitud enviada. Un administrador la aprobará.": "Request sent. An administrator will approve it.",
    "La contraseña actual no es correcta.": "The current password is not correct.",
    "Foto de perfil": "Profile photo",
    "Cambiar foto": "Change photo",
    "Poner foto": "Add photo",
    "Eliminar foto": "Remove photo",
    "¿Eliminar tu foto de perfil?": "Remove your profile photo?",
    "Se volverá a mostrar tu inicial.": "Your initial will be shown again.",
    "Editor de foto": "Photo editor",
    "Rotar": "Rotate",
    "Zoom": "Zoom",
    "Recortar": "Crop",
    "Vista previa": "Preview",
    "Aplicar": "Apply",
    "Cancelar": "Cancel",
    "Eliminar": "Remove",
    "La imagen no se pudo leer.": "The image could not be read.",
    "El archivo supera el tamaño máximo de {mb} MB.": "The file exceeds the maximum size of {mb} MB.",
    "Formato no admitido. Usa PNG, JPG, WEBP o BMP.": "Unsupported format. Use PNG, JPG, WEBP or BMP.",
    "Tema": "Theme",
    "Claro": "Light",
    "Sistema": "System",
    "Oscuro": "Dark",
    "Idioma": "Language",
    "Español": "Spanish",
    "Inglés": "English",
    "Cerrar sesión": "Sign out",
    "Cerrar sesión": "Sign out",
    # ------------------------------------------------ ventana
    "Volver al inicio": "Back to start",
    "Contraer o expandir la barra (Ctrl+B)": "Collapse or expand the sidebar (Ctrl+B)",
    "Sin notificaciones sin leer": "No unread notifications",
    "{n} notificaciones sin leer": "{n} unread notifications",
    "1 notificación sin leer": "1 unread notification",
    "Abrir mi perfil": "Open my profile",
    "Cerrar sesión": "Sign out",
    "Actualizar": "Refresh",
    "Volver a consultar (F5)": "Refresh (F5)",
    "Oracle: conectando…": "Oracle: connecting…",
    "Oracle: conectado": "Oracle: connected",
    "Oracle: sin conexión": "Oracle: offline",
    "Bluetooth: apagado": "Bluetooth: off",
    "Bluetooth: {estado}": "Bluetooth: {estado}",
    "Actualizado {hora}": "Updated {hora}",
    "Inventario": "Inventory",
    "Sincronización lista: {n} lecturas recibidas": "Synchronization complete: {n} readings received",
    "Sincronización lista: 1 lectura recibida": "Synchronization complete: 1 reading received",
    "No se pudo consultar la base de datos.": "The database could not be reached.",
    "Reanudar el servicio Bluetooth cuando quieras.": "Resume the Bluetooth service whenever you want.",
    "Respaldo restaurado.": "Backup restored.",
    # ------------------------------------------------ aviso flotante «Nuevo SKU»
    "Nuevo SKU": "New SKU",
    "Crear y procesar": "Create and process",
    "No crear": "Don't create",
    "SKU": "SKU",
    "Sin SKU": "No SKU",
    "Nombre del producto": "Product name",
    "Categoría": "Category",
    "1 lectura": "1 reading",
    "{n} lecturas": "{n} readings",
    "última {fecha}": "last {fecha}",
    "+{n} más": "+{n} more",
    "Ocultar por ahora (el SKU sigue pendiente)": "Hide for now (the SKU stays pending)",
    "Ocultar aviso": "Hide notice",
    "1 oculto · mostrar": "1 hidden · show",
    "{n} ocultos · mostrar": "{n} hidden · show",
    "El SKU viene en la lectura; no se puede cambiar.": "The SKU comes from the reading; it cannot be changed.",
    "El SKU no está en el catálogo. Al crearlo se le asigna stock 0 y la lectura se procesa.":
        "The SKU is not in the catalog. Creating it sets stock 0 and processes the reading.",
    "El nombre y la categoría son obligatorios.": "Name and category are required.",
    "¿No tomar la lectura?": "Don't take the reading?",
    "El SKU {sku} no se contará.": "SKU {sku} will not be counted.",
    "SKU creado": "SKU created",
    "lectura procesada": "reading processed",
    "Lectura descartada": "Reading discarded",
    # ------------------------------------------------ Sincronización: SKU nuevos
    "Nuevos SKU": "New SKUs",
    "Nuevos SKU: {n}": "New SKUs: {n}",
    "No hay SKU nuevos pendientes de decisión.": "There are no new SKUs waiting for a decision.",
    "Los SKU nuevos esperan tu decisión en el aviso flotante («Crear y procesar» o «No crear»). "
    "Ya no cuentan como error.":
        "New SKUs wait for your decision in the floating notice (“Create and process” or “Don't create”). "
        "They no longer count as errors.",
    "· último procesamiento {fecha} UTC ({origen}) · {pendientes} pendientes, {errores} con error, "
    "{nuevos} nuevos, {descartados} descartados":
        "· last run {fecha} UTC ({origen}) · {pendientes} pending, {errores} with error, "
        "{nuevos} new, {descartados} discarded",
    # ------------------------------------------------ misc
    "Sí": "Yes",
    "No": "No",
    "Guardar": "Save",
    "Buscar": "Search",
    "Todos": "All",
    "Todas": "All",
    "Sin leer": "Unread",
    "Marcar todas como leídas": "Mark all as read",
    "No hay nada que deshacer.": "There is nothing to undo.",
    "Acción deshecha: {texto}": "Action undone: {texto}",
}


def t(texto: str, **kwargs: Any) -> str:
    """Traduce ``texto`` (clave en español) al idioma activo y aplica ``kwargs`` con ``str.format``."""
    traducido = _EN.get(texto, texto) if _IDIOMA == "en" else texto
    if kwargs:
        try:
            return traducido.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return traducido
    return traducido


def registrar(traducciones: dict[str, str]) -> None:
    """Aporta traducciones desde otro módulo (español → inglés). No pisa las existentes."""
    for espanol, ingles in traducciones.items():
        _EN.setdefault(espanol, ingles)


def idioma() -> str:
    return _IDIOMA


def idioma_actual() -> str:
    return _IDIOMA


def set_idioma(nuevo: str) -> None:
    """Fija el idioma activo (``es`` o ``en``). No persiste: eso lo hace auth/Perfil."""
    global _IDIOMA
    _IDIOMA = nuevo if nuevo in IDIOMAS else "es"


def decimal(valor: float, decimales: int = 1) -> str:
    """Número con decimales según el idioma: «83,3» en español, «83.3» en inglés."""
    texto = f"{valor:.{decimales}f}"
    return texto.replace(".", ",") if _IDIOMA == "es" else texto


def miles(valor: float, decimales: int = 0) -> str:
    """Número con separador de miles según el idioma: «11.800» en español, «11,800» en inglés."""
    texto = f"{valor:,.{decimales}f}"
    if _IDIOMA == "es":
        texto = texto.replace(",", "§").replace(".", ",").replace("§", ".")
    return texto


def porcentaje(valor: float, decimales: int = 1) -> str:
    """«83,3 %» en español, «83.3%» en inglés."""
    return decimal(valor, decimales) + (" %" if _IDIOMA == "es" else "%")


def nombre_idioma(codigo: str) -> str:
    return NOMBRE_IDIOMA.get(codigo, codigo)


# Traducciones de las vistas de identidad y navegación (se registran al importar el módulo).
registrar({
    "Accede con tu cuenta del PC.": "Sign in with your PC account.",
    "escuchando": "listening", "esperando el código": "waiting for the code", "celular conectado": "phone connected",
    "recibiendo": "receiving", "procesando": "processing", "listo": "ready", "error": "error",
    "pausando": "pausing", "en pausa": "paused", "servicio detenido": "service stopped",
    "Apariencia": "Appearance",
    "Ajustar": "Fit",
    "Cerrar": "Close",
    "Cargando la foto…": "Loading photo…",
    "Rueda: zoom · arrastra: mover · doble clic: ajustar": "Wheel: zoom · drag: move · double click: fit",
    "Desvincular": "Unlink",
    "Editor de foto": "Photo editor",
    "Elegir foto": "Choose photo",
    "Elige una pregunta de seguridad.": "Choose a security question.",
    "Elige una pregunta…": "Choose a question…",
    "Eliminar": "Remove",
    "Eliminar foto": "Remove photo",
    "¿Eliminar tu foto de perfil?": "Remove your profile photo?",
    "El Administrador debe aprobar el cambio en Solicitudes.": "The Administrator must approve the change in Requests.",
    "El Administrador no se puede suspender.": "The Administrator cannot be suspended.",
    "El Administrador responde su pregunta de seguridad. Inventario deja la solicitud para aprobación.":
        "The Administrator answers the security question. Inventory leaves the request for approval.",
    "El archivo no es una imagen válida.": "The file is not a valid image.",
    "El archivo supera el tamaño máximo de {mb} MB.": "The file exceeds the maximum size of {mb} MB.",
    "Esta cuenta no usa pregunta de seguridad: la solicitud se enviará para aprobación.":
        "This account does not use a security question: the request will be sent for approval.",
    "Escribe tu usuario.": "Write your username.",
    "Escribe tu usuario y tu contraseña.": "Write your username and password.",
    "Foto de perfil actualizada.": "Profile photo updated.",
    "La cuenta del celular queda libre para el próximo teléfono que sincronice con ella.":
        "The phone account becomes free for the next phone that synchronizes with it.",
    "La cuenta quedará libre para el próximo teléfono que sincronice.":
        "The account will be free for the next phone that synchronizes.",
    "La fila del Administrador está bloqueada: siempre tiene Gestión.":
        "The Administrator row is locked: it always has Manage.",
    "La imagen no se pudo leer.": "The image could not be read.",
    "La ruta de la foto no es válida.": "The photo path is not valid.",
    "Las contraseñas no coinciden.": "The passwords do not match.",
    "Las personas con cuenta aprobada. Aquí se suspende una cuenta (con motivo) o se reactiva, "
    "se pone una contraseña nueva a las cuentas del PC y se desvincula el teléfono. Las cuentas "
    "nuevas se aprueban en «Solicitudes».":
        "People with an approved account. Suspend (with a reason) or reactivate an account here, "
        "set a new password for PC accounts and unlink the phone. New accounts are approved in Requests.",
    "Módulo": "Module",
    "Mostrar contraseña": "Show password",
    "Ocultar contraseña": "Hide password",
    "Motivo: {motivo}": "Reason: {motivo}",
    "Ningún empleado coincide con el filtro": "No employee matches the filter",
    "No hay otro rol disponible para esta cuenta.": "No other role is available for this account.",
    "No se pudo guardar el cambio. Se volvió a leer la matriz.":
        "The change could not be saved. The matrix was reloaded.",
    "No se pudo guardar la preferencia.": "The preference could not be saved.",
    "Poner foto": "Add photo",
    "Poner contraseña nueva…": "Set new password…",
    "Pregunta: {pregunta}": "Question: {pregunta}",
    "Qué puede hacer cada rol en cada módulo. «Consulta» lo ve; «Gestión» además cambia datos. "
    "El cambio rige desde el próximo inicio de sesión de cada persona. El Administrador siempre "
    "gestiona los doce módulos y su fila está bloqueada.":
        "What each role can do in each module. View means it is visible; Manage also changes data. "
        "The change applies from each person's next sign-in. The Administrator always manages all "
        "twelve modules and their row is locked.",
    "Quien se registra (en el PC o en el celular) espera aquí. Elige su rol y apruébala, o "
    "recházala con un motivo que verá al intentar entrar. Los cambios de contraseña de Perfil "
    "también se aprueban aquí.":
        "Whoever registers (on the PC or the phone) waits here. Choose their role and approve them, "
        "or reject them with a reason they will see when signing in. Profile password changes are "
        "also approved here.",
    "Registrada el {fecha}": "Registered on {fecha}",
    "Reactivar": "Reactivate",
    "Restablecer": "Reset",
    "Se volverá a mostrar tu inicial.": "Your initial will be shown again.",
    "Sin empleados todavía": "No employees yet",
    "Solo el Administrador usa pregunta de seguridad. Si eres Inventario, la solicitud va a aprobación.":
        "Only the Administrator uses a security question. If you are Inventory, the request goes to approval.",
    "Solo existe un Administrador; las cuentas del PC solo pueden ser de Inventario.":
        "There is only one Administrator; PC accounts can only have the Inventory role.",
    "Solicitar cambio de contraseña": "Request password change",
    "Tu contraseña cambia de inmediato.": "Your password changes immediately.",
    "Volver al acceso": "Back to sign-in",
    "Todos los estados": "All states",
    "Todos los roles": "All roles",
    "¿Ya la recuerdas?": "Remembered it?",
    "¿Ya tienes cuenta?": "Already have an account?",
    "¿No tienes cuenta?": "Don't have an account?",
})

registrar({
    "¿Cuál es el nombre de tu primera mascota?": "What was your first pet's name?",
    "¿En qué ciudad naciste?": "What city were you born in?",
    "¿Cuál es el nombre de tu mejor amigo de la infancia?": "What was your childhood best friend's name?",
    "¿Cuál fue tu primer colegio?": "What was your first school?",
    "¿Cuál es tu comida favorita?": "What is your favorite food?",
})

registrar({
    "GESTIÓN DE INVENTARIO": "INVENTORY MANAGEMENT",
    "BIENVENIDO": "WELCOME",
    "Conteo físico sin red.\nEl PC recibe por Bluetooth y Oracle concilia.":
        "Physical counting, offline.\nThe PC receives over Bluetooth and Oracle reconciles.",
    "Android · Bluetooth · Oracle": "Android · Bluetooth · Oracle",
    "Recordar usuario": "Remember username",
    "o": "or",
    "Volver a iniciar sesión": "Back to sign in",
    "Recuperar contraseña": "Recover password",
    "Seguridad de la contraseña": "Password strength",
    "12 caracteres o más": "12 characters or more",
    "Mayúscula y minúscula": "Upper and lower case",
    "Al menos un número": "At least one number",
    "Al menos un símbolo": "At least one symbol",
    "Vacía": "Empty",
    "Regular": "Fair",
    "Patrón comúnmente adivinado": "Commonly guessed pattern",
    "Escribe tu usuario y pulsa Ver pregunta.": "Write your username and click Show question.",
    "Ver pregunta": "Show question",
})

registrar({
    "Apariencia e idioma": "Appearance and language",
    "Ajustes": "Settings",
    "Usuario o contraseña incorrectos.": "Incorrect username or password.",
    "Ese usuario ya existe.": "That username already exists.",
    "Ese correo ya está en uso.": "That email is already in use.",
    "El correo no es válido.": "That email address is not valid.",
    "El usuario debe tener de 3 a 30 caracteres: letras, números, punto o guion.":
        "The username must have 3 to 30 characters: letters, numbers, dot or dash.",
    "Escribe tu nombre completo (máximo 60 caracteres).": "Write your full name (maximum 60 characters).",
    "La contraseña necesita mínimo 8 caracteres.": "The password needs at least 8 characters.",
    "La contraseña debe tener letras y números.": "The password must have letters and numbers.",
    "Las dos contraseñas no coinciden.": "The two passwords do not match.",
    "Los operadores usan la app móvil.": "Operators use the mobile app.",
    "La respuesta de seguridad no es correcta.": "The security answer is not correct.",
    "Contraseña cambiada. Entra con la nueva.": "Password changed. Sign in with the new one.",
    "Solicitud enviada. Un administrador la revisará.": "Request sent. An administrator will review it.",
    "Elige una pregunta de seguridad.": "Choose a security question.",
    "Escribe la respuesta de seguridad.": "Write the security answer.",
    "Los operadores no recuperan su contraseña desde el escritorio.":
        "Operators do not recover their password from the desktop app.",
    "El usuario o la contraseña no son correctos.": "The username or password is not correct.",
})
