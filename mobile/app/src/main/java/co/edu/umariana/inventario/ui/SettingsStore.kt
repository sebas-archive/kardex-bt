package co.edu.umariana.inventario.ui

import android.content.Context

/**
 * Ajustes que la app recuerda entre aperturas: operador (D20), conteo en curso y el PC
 * al que se conectó la última vez (D22: desde entonces conecta directo, sin buscar).
 */
class SettingsStore(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("ajustes", Context.MODE_PRIVATE)

    var operador: String
        get() = prefs.getString("operador", "") ?: ""
        set(valor) = prefs.edit().putString("operador", valor).apply()

    var conteo: String?
        get() = prefs.getString("conteo", null)
        set(valor) = prefs.edit().putString("conteo", valor).apply()

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

    fun abrirSesion(usuario: String, nombre: String, rol: String, estado: String, motivo: String?) {
        prefs.edit().putString("sesion_usuario", usuario).putString("sesion_nombre", nombre).putString("sesion_rol", rol)
            .putString("sesion_estado", estado).putString("sesion_motivo", motivo).apply()
    }

    fun cerrarSesion() {
        prefs.edit().remove("sesion_usuario").remove("sesion_nombre").remove("sesion_rol")
            .remove("sesion_estado").remove("sesion_motivo").apply()
    }

    fun olvidarPc() {
        prefs.edit().remove("pc_direccion").remove("pc_nombre").apply()
    }
}
