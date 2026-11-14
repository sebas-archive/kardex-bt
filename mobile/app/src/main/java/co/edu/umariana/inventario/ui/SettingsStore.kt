package co.edu.umariana.inventario.ui

import android.content.Context

/**
 * Ajustes que la app recuerda entre aperturas: operador, el PC al que se conectó la última vez (D22: desde entonces
 * conecta directo, sin buscar), la sesión abierta y las preferencias de apariencia de cada usuario.
 */
class SettingsStore(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("ajustes", Context.MODE_PRIVATE)

    var operador: String
        get() = prefs.getString("operador", "") ?: ""
        set(valor) = prefs.edit().putString("operador", valor).apply()

    /** Dirección Bluetooth del PC recordado, o null si todavía no se eligió ninguno. */
    var pcDireccion: String?
        get() = prefs.getString("pc_direccion", null)
        set(valor) = prefs.edit().putString("pc_direccion", valor).apply()

    var pcNombre: String?
        get() = prefs.getString("pc_nombre", null)
        set(valor) = prefs.edit().putString("pc_nombre", valor).apply()

    /** Sesión abierta: quién entró en el teléfono (null si nadie). El nombre y el rol se guardan para no ir a la base en cada pantalla. */
    val sesionUsuario: String? get() = prefs.getString("sesion_usuario", null)
    val sesionNombre: String? get() = prefs.getString("sesion_nombre", null)
    val sesionRol: String? get() = prefs.getString("sesion_rol", null)
    val sesionEstado: String? get() = prefs.getString("sesion_estado", null)
    val sesionMotivo: String? get() = prefs.getString("sesion_motivo", null)
    val sesionCorreo: String? get() = prefs.getString("sesion_correo", null)
    val sesionFoto: String? get() = prefs.getString("sesion_foto", null)

    fun abrirSesion(usuario: String, nombre: String, rol: String, estado: String, motivo: String?,
                    correo: String? = null, foto: String? = null) {
        prefs.edit().putString("sesion_usuario", usuario).putString("sesion_nombre", nombre).putString("sesion_rol", rol)
            .putString("sesion_estado", estado).putString("sesion_motivo", motivo)
            .putString("sesion_correo", correo).putString("sesion_foto", foto).apply()
    }

    /** Actualiza solo la foto de la sesión (al ponerla o quitarla sin volver a entrar). */
    fun actualizarFoto(ruta: String?) {
        prefs.edit().putString("sesion_foto", ruta).apply()
    }

    fun cerrarSesion() {
        prefs.edit().remove("sesion_usuario").remove("sesion_nombre").remove("sesion_rol")
            .remove("sesion_estado").remove("sesion_motivo").remove("sesion_correo").remove("sesion_foto").apply()
    }

    fun olvidarPc() {
        prefs.edit().remove("pc_direccion").remove("pc_nombre").apply()
    }

    // ------------------------------------------------------------------ tema e idioma por usuario
    /** Tema de ese usuario: `CLARO`, `SISTEMA` u `OSCURO`. */
    fun tema(usuario: String?): String = prefs.getString(clave("tema", usuario), TEMA_SISTEMA) ?: TEMA_SISTEMA

    fun guardarTema(usuario: String?, valor: String) = prefs.edit().putString(clave("tema", usuario), valor).apply()

    /** Idioma de ese usuario: `es` o `en`. */
    fun idioma(usuario: String?): String = prefs.getString(clave("idioma", usuario), "es") ?: "es"

    fun guardarIdioma(usuario: String?, valor: String) = prefs.edit().putString(clave("idioma", usuario), valor).apply()

    private fun clave(nombre: String, usuario: String?): String =
        "${nombre}_${usuario?.lowercase()?.takeIf { it.isNotBlank() } ?: "invitado"}"

    companion object {
        const val TEMA_CLARO = "CLARO"
        const val TEMA_SISTEMA = "SISTEMA"
        const val TEMA_OSCURO = "OSCURO"
        val TEMAS = listOf(TEMA_CLARO, TEMA_SISTEMA, TEMA_OSCURO)
    }
}
