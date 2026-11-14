package co.edu.umariana.inventario.ui

import co.edu.umariana.inventario.auth.EstadoCuenta
import co.edu.umariana.inventario.auth.Rol
import co.edu.umariana.inventario.data.Estado
import co.edu.umariana.inventario.data.NotificacionEntity
import co.edu.umariana.inventario.data.TipoAviso

/**
 * Traducciones de la interfaz. La app se escribió en español; cada texto visible pasa por [t], que devuelve el
 * inglés cuando el usuario eligió `en`. Los textos con datos usan plantillas con `{n}`, `{nombre}`, etc.
 */
object Textos {
    val idioma: String get() = Apariencia.idioma

    fun t(es: String): String = if (idioma == "en") EN[es] ?: es else es

    fun t(es: String, vararg datos: Pair<String, Any?>): String {
        var texto = t(es)
        for ((clave, valor) in datos) texto = texto.replace("{$clave}", valor?.toString().orEmpty())
        return texto
    }

    /** Singular o plural según [cantidad]; la plantilla recibe `{n}`. */
    fun n(cantidad: Int, singular: String, plural: String): String =
        t(if (cantidad == 1) singular else plural).replace("{n}", cantidad.toString())

    fun rol(rol: String): String = t(Rol.nombre(rol))

    fun estadoCuenta(estado: String): String = t(
        when (estado) {
            EstadoCuenta.PENDIENTE -> "Pendiente"
            EstadoCuenta.ACTIVO -> "Activa"
            EstadoCuenta.RECHAZADO -> "Rechazada"
            EstadoCuenta.SUSPENDIDO -> "Suspendida"
            else -> estado
        }
    )

    fun estadoLectura(estado: String): String = t(
        when (estado) {
            Estado.CONFIRMADO -> "Confirmada"
            Estado.ENVIADO -> "Enviada"
            else -> "Pendiente"
        }
    )

    fun estadoLecturaPlural(estado: String): String = t(
        when (estado) {
            Estado.CONFIRMADO -> "Confirmadas"
            Estado.ENVIADO -> "Enviadas"
            else -> "Pendientes"
        }
    )

    fun tema(valor: String): String = t(
        when (valor) {
            SettingsStore.TEMA_CLARO -> "Claro"
            SettingsStore.TEMA_OSCURO -> "Oscuro"
            else -> "Sistema"
        }
    )

    fun idiomaNombre(valor: String): String = t(if (valor == "en") "Inglés" else "Español")

    fun tituloAviso(aviso: NotificacionEntity): String = t(
        when (aviso.tipo) {
            TipoAviso.CUENTA_CREADA -> "Cuenta creada"
            TipoAviso.CUENTA_ACTIVA -> "Cuenta aprobada"
            TipoAviso.CUENTA_PENDIENTE -> "Tu cuenta sigue pendiente"
            TipoAviso.CUENTA_SUSPENDIDA -> "Cuenta suspendida"
            TipoAviso.CUENTA_RECHAZADA -> "Cuenta rechazada"
            TipoAviso.CLAVE_RESTABLECIDA -> "Contraseña restablecida"
            TipoAviso.SYNC_OK -> "Sincronización completada"
            TipoAviso.SYNC_CON_PENDIENTES -> "Sincronización incompleta"
            TipoAviso.SYNC_SIN_CONEXION -> "No se pudo sincronizar"
            TipoAviso.CATALOGO_ACTUALIZADO -> "Catálogo actualizado"
            else -> "Aviso"
        }
    )

    fun detalleAviso(aviso: NotificacionEntity): String {
        val dato = aviso.dato
        return t(
            when (aviso.tipo) {
                TipoAviso.CUENTA_CREADA -> "Queda pendiente de aprobación en el PC. Sincroniza para enviarla."
                TipoAviso.CUENTA_ACTIVA -> "Ya puedes contar y sincronizar."
                TipoAviso.CUENTA_PENDIENTE -> "El administrador debe aprobarla en el PC."
                TipoAviso.CUENTA_SUSPENDIDA -> "Motivo: {motivo}"
                TipoAviso.CUENTA_RECHAZADA -> "Motivo: {motivo}"
                TipoAviso.CLAVE_RESTABLECIDA -> "Entra con tu nueva contraseña."
                TipoAviso.SYNC_OK -> "{n} lecturas aceptadas."
                TipoAviso.SYNC_CON_PENDIENTES -> "Quedan {n} lecturas por enviar."
                TipoAviso.SYNC_SIN_CONEXION -> "Revisa que el PC esté cerca y con la sincronización iniciada."
                TipoAviso.CATALOGO_ACTUALIZADO -> "{n} productos disponibles."
                else -> dato
            },
            "motivo" to dato.ifBlank { t("Sin motivo") },
            "n" to dato,
        )
    }

    private val EN: Map<String, String> = mapOf(
        // ---------------------------------------------------------------- común
        "Inventario" to "Inventory",
        "Volver" to "Back",
        "Cancelar" to "Cancel",
        "Guardar" to "Save",
        "Continuar" to "Continue",
        "Iniciar" to "Start",
        "Eliminar" to "Delete",
        "Cambiar" to "Change",
        "Buscar" to "Search",
        "Sí" to "Yes",
        "No" to "No",
        "Sin motivo" to "No reason",
        "Pendiente" to "Pending",
        "Activa" to "Active",
        "Rechazada" to "Rejected",
        "Suspendida" to "Suspended",
        "Confirmada" to "Confirmed",
        "Enviada" to "Sent",
        "Confirmadas" to "Confirmed",
        "Enviadas" to "Sent",
        "Pendientes" to "Pending",
        "Claro" to "Light",
        "Oscuro" to "Dark",
        "Sistema" to "System",
        "Español" to "Spanish",
        "Inglés" to "English",
        "Operador de Inventario" to "Inventory Operator",
        "SKU fuera del catálogo" to "SKU not in catalog",
        "Corregir" to "Correct",
        "Conteo actual" to "Current count",
        "Tema" to "Theme",
        "Idioma" to "Language",
        "Correo" to "Email",
        "Sin correo" to "No email",
        "Rol" to "Role",

        "1 sin leer" to "1 unread",
        "{n} sin leer" to "{n} unread",
        "Apunta al código de barras o al QR" to "Point at the barcode or QR",
        "Motivo: {m}. " to "Reason: {m}. ",
        "Se guardará un cuadrado; el avatar se muestra circular." to
            "A square will be saved; the avatar is shown circular.",
        "Tus {n} lecturas siguen guardadas." to "Your {n} readings are still stored.",
        "{n} lectura aceptada" to "{n} reading accepted",
        "{n} lectura por enviar." to "{n} reading to send.",
        "Recuperar contraseña" to "Recover password",
        "Foto adjunta" to "Attached photo",
        // ---------------------------------------------------------------- acceso
        "Entra para empezar a contar" to "Sign in to start counting",
        "Crea tu cuenta en este teléfono" to "Create your account on this phone",
        "Recupera tu contraseña" to "Recover your password",
        "Usuario" to "Username",
        "Contraseña" to "Password",
        "Ocultar contraseña" to "Hide password",
        "Mostrar contraseña" to "Show password",
        "Iniciar sesión" to "Sign in",
        "Entrar" to "Sign in",
        "¿Olvidaste tu contraseña?" to "Forgot your password?",
        "Crear cuenta" to "Create account",
        "Nombre completo" to "Full name",
        "Aparece como operador en cada lectura" to "Shown as the operator on each reading",
        "3 a 20: letras, números, punto o guion" to "3 to 20: letters, numbers, dot or dash",
        "Repite la contraseña" to "Repeat the password",
        "Tu cuenta quedará pendiente hasta que el administrador la apruebe en el PC. Se entera al sincronizar." to
            "Your account stays pending until the administrator approves it on the PC. The phone finds out when it syncs.",
        "Tu respuesta" to "Your answer",
        "Sirve para recuperar la contraseña sin internet" to "Used to recover your password without internet",
        "Ya tengo cuenta" to "I already have an account",
        "Responde la pregunta de seguridad que elegiste al crear la cuenta." to
            "Answer the security question you chose when you created the account.",
        "Tu pregunta" to "Your question",
        "Contraseña nueva" to "New password",
        "Repite la contraseña nueva" to "Repeat the new password",
        "Buscar mi pregunta" to "Find my question",
        "Cambiar contraseña" to "Change password",
        "Volver a entrar" to "Back to sign in",
        "Mínimo 8 caracteres, con letras y números" to "At least 8 characters, with letters and numbers",
        "Todavía no: mínimo 8 caracteres, con letras y números" to "Not yet: at least 8 characters, with letters and numbers",
        "Aceptable" to "Acceptable",
        "Buena" to "Good",
        "Fuerte" to "Strong",
        "Pregunta de seguridad" to "Security question",
        "Las cuentas se guardan en este teléfono: la app funciona sin red." to
            "Accounts are stored on this phone: the app works offline.",
        "Correo (opcional)" to "Email (optional)",
        "No se usa para entrar; es un dato de perfil" to "Not used to sign in; it is profile data",
        "¿Cuál es el nombre de tu primera mascota?" to "What was the name of your first pet?",
        "¿En qué ciudad naciste?" to "What city were you born in?",
        "¿Cuál es el segundo nombre de tu madre?" to "What is your mother's middle name?",
        "¿Cómo se llamaba tu primera escuela?" to "What was the name of your first school?",
        "¿Cuál es tu comida favorita?" to "What is your favorite food?",
        "¡Hola, {nombre}!" to "Hi, {nombre}!",
        "Contraseña restablecida. Entra con la nueva." to "Password reset. Sign in with the new one.",

        // ---------------------------------------------------------------- inicio
        "Hola," to "Hi,",
        "Mi cuenta" to "My account",
        "lectura por enviar" to "reading to send",
        "lecturas por enviar" to "readings to send",
        "{n} lecturas por enviar" to "{n} readings to send",
        "{n} guardadas en el teléfono" to "{n} stored on the phone",
        "📷 1 foto por enviar" to "📷 1 photo to send",
        "📷 {n} fotos por enviar" to "📷 {n} photos to send",
        "Todavía no hay catálogo. Sincroniza una vez con el PC para descargarlo." to
            "There is no catalog yet. Sync once with the PC to download it.",
        "Sincronizar" to "Sync",
        "Contar" to "Count",
        "Escanear barras o QR, o digitar" to "Scan barcodes or QR, or type",
        "Contado" to "Counted",
        "Lo que has contado" to "What you have counted",
        "Nada por enviar" to "Nothing to send",
        "{n} por enviar" to "{n} to send",
        "Sincronizar con el PC" to "Sync with the PC",
        "Todo enviado" to "All sent",
        "{n} lecturas esperando · sin claves ni códigos" to "{n} readings waiting · no passwords or codes",
        "Catálogo" to "Catalog",
        "Productos del catálogo" to "Catalog products",
        "Notificaciones" to "Notifications",
        "Abrir notificaciones" to "Open notifications",

        // ---------------------------------------------------------------- catálogo
        "{n} productos" to "{n} products",
        "Buscar por SKU o nombre" to "Search by SKU or name",
        "No hay productos en el catálogo" to "There are no products in the catalog",
        "Sincroniza con el PC para descargarlo." to "Sync with the PC to download it.",
        "Sin resultados" to "No results",
        "No hay productos que coincidan con «{q}»." to "No products match “{q}”.",
        "Toca un producto para contarlo" to "Tap a product to count it",

        // ---------------------------------------------------------------- contar
        "Corregir lectura" to "Correct reading",
        "Guardar corrección" to "Save correction",
        "{n} guardadas en esta sesión" to "{n} saved in this session",
        "SKU, código de barras o QR" to "SKU, barcode or QR",
        "Se puede guardar igual; quedará pendiente de darlo de alta." to
            "You can still save it; it will stay pending until it is added.",
        "Ya contado: {n}. Guardar lo reemplaza." to "Already counted: {n}. Saving replaces it.",
        "Dañados o defectuosos (opcional)" to "Damaged or defective (optional)",
        "De las unidades contadas, cuántas están dañadas" to "How many of the counted units are damaged",
        "Nota (opcional)" to "Note (optional)",
        "Foto de evidencia (opcional)" to "Evidence photo (optional)",
        "📷  Cámara" to "📷  Camera",
        "Galería" to "Gallery",
        "Se adjuntará al guardar" to "It will be attached when you save",
        "Quitar" to "Remove",
        "Escanear código de barras o QR" to "Scan barcode or QR",
        "Con la cámara · funciona sin red" to "With the camera · works offline",
        "Cantidad" to "Quantity",
        "Cantidad ({u})" to "Quantity ({u})",
        "Restar uno" to "Subtract one",
        "Sumar uno" to "Add one",
        "Guardado" to "Saved",
        "No se pudo leer esa foto" to "That photo could not be read",
        "Ese código no trae un SKU" to "That code does not contain an SKU",
        "Sin permiso de cámara: escribe el SKU a mano" to "No camera permission: type the SKU by hand",
        "Sin permiso de cámara: elige la foto de la galería" to "No camera permission: choose a photo from the gallery",

        // ---------------------------------------------------------------- listas
        "{n} productos contados" to "{n} products counted",
        "Contar otro producto" to "Count another product",
        "Aún no has contado nada" to "You have not counted anything yet",
        "Cada producto que guardes aparece en esta lista. Tocar uno permite corregir su cantidad." to
            "Every product you save appears in this list. Tap one to correct its quantity.",
        "{n} dañados" to "{n} damaged",
        "{n} lecturas en el teléfono" to "{n} readings on the phone",
        "Sincronizar {n} lecturas" to "Sync {n} readings",
        "Todavía no hay lecturas" to "There are no readings yet",
        "Lo que cuentes se guarda en el teléfono y aparece aquí hasta que el PC lo confirme." to
            "What you count is stored on the phone and appears here until the PC confirms it.",

        // ---------------------------------------------------------------- sincronizar
        "Bluetooth · sin wifi" to "Bluetooth · no Wi-Fi",
        "Sincronizando…" to "Syncing…",
        "Sincronizar ahora" to "Sync now",
        "Buscando el PC…" to "Looking for the PC…",
        "En el PC pulsa «Iniciar sincronización». Aparece como {pc}." to
            "On the PC press “Start sync”. It appears as {pc}.",
        "Elige el PC" to "Choose the PC",
        "Solo la primera vez hay que buscarlo; después conecta solo, sin claves ni códigos." to
            "You only have to look for it the first time; after that it connects by itself, without passwords or codes.",
        "Listo para sincronizar" to "Ready to sync",
        "{n} lecturas por enviar." to "{n} readings to send.",
        "No hay lecturas por enviar; se actualizará el catálogo." to
            "There are no readings to send; the catalog will be updated.",
        "Conectando…" to "Connecting…",
        "Intento {i} de 3 · sin claves ni códigos." to "Attempt {i} of 3 · no passwords or codes.",
        "Enviando lecturas" to "Sending readings",
        "{n} de {m} confirmadas por el PC." to "{n} of {m} confirmed by the PC.",
        "Reintentando…" to "Retrying…",
        "Se cortó la conexión. Intento {i} de 3." to "The connection dropped. Attempt {i} of 3.",
        "¡Listo!" to "Done!",
        "{n} lecturas aceptadas" to "{n} readings accepted",
        ", {n} líneas reenviadas" to ", {n} lines resent",
        ". Quedan {n} sin enviar: vuelve a sincronizar." to ". {n} are still unsent: sync again.",
        ". Todo quedó en el PC." to ". Everything is on the PC.",
        "PC ocupado" to "PC busy",
        "Está atendiendo a otro teléfono. Espera a que termine y vuelve a intentar." to
            "It is serving another phone. Wait for it to finish and try again.",
        "El PC rechazó la conexión" to "The PC rejected the connection",
        "No se pudo conectar" to "Could not connect",
        "¿El PC está encendido, cerca y con la sincronización iniciada?" to
            "Is the PC on, nearby and with sync started?",
        "Se cortó la conexión" to "The connection dropped",
        "Las {n} lecturas sin enviar siguen guardadas. Vuelve a intentar." to
            "The {n} unsent readings are still stored. Try again.",
        "Tu cuenta espera aprobación" to "Your account is awaiting approval",
        "El administrador debe aprobarla en el PC. Tus {n} lecturas siguen guardadas." to
            "The administrator must approve it on the PC. Your {n} readings are still stored.",
        "Tu cuenta está {estado}" to "Your account is {estado}",
        "Motivo: {motivo}. Tus {n} lecturas siguen guardadas." to
            "Reason: {motivo}. Your {n} readings are still stored.",
        "enviado" to "sent",
        "Sin PC elegido" to "No PC chosen",
        "Búscalo con el PC esperando" to "Find it with the PC waiting",
        "{direccion} · toca para conectar" to "{direccion} · tap to connect",
        "Sin permiso de Bluetooth. Actívalo en Ajustes > Aplicaciones > Inventario > Permisos." to
            "No Bluetooth permission. Enable it in Settings > Apps > Inventory > Permissions.",
        "El Bluetooth sigue apagado." to "Bluetooth is still off.",
        "Este teléfono no tiene Bluetooth." to "This phone does not have Bluetooth.",
        "Enciende el Bluetooth para sincronizar." to "Turn on Bluetooth to sync.",
        "No encontré «{pc}». En el PC pulsa «Iniciar sincronización» y acércate. En Android 10 o anterior la ubicación del teléfono debe estar encendida para buscar." to
            "I did not find “{pc}”. On the PC press “Start sync” and come closer. On Android 10 or older, phone location must be on to search.",

        // ---------------------------------------------------------------- mi cuenta
        "Lo que puede hacer tu rol" to "What your role can do",
        "Contar y clasificar productos" to "Count and classify products",
        "Contar productos" to "Count products",
        "Sincronizar con el PC configurado" to "Sync with the configured PC",
        "Cambiar el PC del teléfono" to "Change the phone's PC",
        "Cerrar sesión" to "Sign out",
        "Las lecturas guardadas no se pierden al cerrar sesión." to "Stored readings are not lost when you sign out.",
        "Foto de perfil" to "Profile photo",
        "Poner foto" to "Add photo",
        "Cambiar foto" to "Change photo",
        "Eliminar foto" to "Delete photo",
        "¿Eliminar la foto de perfil?" to "Delete profile photo?",
        "Se perderá la foto actual y volverá a mostrarse tu inicial." to
            "The current photo will be lost and your initial will be shown again.",
        "Editar foto" to "Edit photo",
        "Rotar" to "Rotate",
        "Cortar" to "Crop",
        "Zoom" to "Zoom",
        "Vista previa" to "Preview",
        "Arrastra para encuadrar" to "Drag to frame",
        "La foto supera el máximo de 2 MB" to "The photo exceeds the 2 MB limit",
        "Elige una imagen JPEG, PNG o WebP" to "Choose a JPEG, PNG or WebP image",
        "No se pudo leer la imagen" to "The image could not be read",
        "Eliminar foto de perfil" to "Delete profile photo",
        "Cuenta" to "Account",
        "Preferencias" to "Preferences",

        // ---------------------------------------------------------------- notificaciones
        "Todas" to "All",
        "Sin leer" to "Unread",
        "Marcar todas como leídas" to "Mark all as read",
        "No hay notificaciones" to "There are no notifications",
        "Aquí verás los avisos del sistema y de la sincronización." to
            "System and sync notices will appear here.",
        "No tienes avisos sin leer" to "You have no unread notices",
        "No hay avisos en esta categoría." to "There are no notices in this category.",
        "Cuenta creada" to "Account created",
        "Cuenta aprobada" to "Account approved",
        "Tu cuenta sigue pendiente" to "Your account is still pending",
        "Cuenta suspendida" to "Account suspended",
        "Cuenta rechazada" to "Account rejected",
        "Contraseña restablecida" to "Password reset",
        "Sincronización completada" to "Sync completed",
        "Sincronización incompleta" to "Incomplete sync",
        "No se pudo sincronizar" to "Could not sync",
        "Catálogo actualizado" to "Catalog updated",
        "Queda pendiente de aprobación en el PC. Sincroniza para enviarla." to
            "It is pending approval on the PC. Sync to send it.",
        "Ya puedes contar y sincronizar." to "You can now count and sync.",
        "El administrador debe aprobarla en el PC." to "The administrator must approve it on the PC.",
        "Motivo: {motivo}" to "Reason: {motivo}",
        "Entra con tu nueva contraseña." to "Sign in with your new password.",
        "{n} lecturas aceptadas." to "{n} readings accepted.",
        "Quedan {n} lecturas por enviar." to "{n} readings are still unsent.",
        "Revisa que el PC esté cerca y con la sincronización iniciada." to
            "Check that the PC is nearby and has sync started.",
        "{n} productos disponibles." to "{n} products available.",
        "Aviso" to "Notice",

        // ---------------------------------------------------------------- estado de cuenta
        "Tu cuenta espera aprobación del administrador" to "Your account is awaiting administrator approval",
        "El administrador rechazó tu solicitud de cuenta" to "The administrator rejected your account request",
        "El administrador suspendió tu cuenta" to "The administrator suspended your account",
        "Motivo: {m}" to "Reason: {m}",
        "Registrada el {fecha}" to "Registered on {fecha}",
        "Regresar al inicio de sesión" to "Back to sign in",
        "Comprobar estado" to "Check status",

        // ---------------------------------------------------------------- mensajes
        "Recuento guardado: reemplaza la lectura anterior" to "Recount saved: it replaces the previous reading",
        "Inicia sesión de nuevo: falta el nombre del operador" to "Sign in again: the operator name is missing",
        "Escanea o escribe el SKU" to "Scan or type the SKU",
        "Cantidad inválida: usa números con punto decimal (hasta 9 enteros y 3 decimales)" to
            "Invalid quantity: use numbers with a decimal point (up to 9 whole digits and 3 decimals)",
        "La nota admite hasta {n} caracteres" to "The note allows up to {n} characters",
        "Los dañados deben ser un número (punto decimal) y no más que la cantidad" to
            "Damaged units must be a number (decimal point) and no more than the quantity",
        "El usuario debe tener de 3 a 20 caracteres: letras, números, punto o guion" to
            "The username must be 3 to 20 characters: letters, numbers, dot or dash",
        "Escribe tu nombre completo (máximo 60 caracteres)" to "Enter your full name (maximum 60 characters)",
        "Escribe un correo válido (máximo 120 caracteres)" to "Enter a valid email (maximum 120 characters)",
        "La contraseña necesita mínimo 8 caracteres, con letras y números" to
            "The password needs at least 8 characters, with letters and numbers",
        "Las dos contraseñas no coinciden" to "The two passwords do not match",
        "Elige una pregunta de seguridad" to "Choose a security question",
        "Escribe la respuesta a la pregunta de seguridad" to "Write the answer to the security question",
        "Ese usuario ya existe en este teléfono" to "That username already exists on this phone",
        "Usuario o contraseña incorrectos" to "Incorrect username or password",
        "Demasiados intentos. Espera {n} segundos y vuelve a probar" to
            "Too many attempts. Wait {n} seconds and try again",
        "No hay una cuenta con ese usuario en este teléfono" to "There is no account with that username on this phone",
        "La respuesta no coincide" to "The answer does not match",
    )
}
