package co.edu.umariana.inventario.ui

import android.content.Context

/**
 * Ajustes que la app recuerda entre aperturas: operador (D20), conteo y ubicación en curso y el PC
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

    var ubicacion: String?
        get() = prefs.getString("ubicacion", null)
        set(valor) = prefs.edit().putString("ubicacion", valor).apply()

    /** Dirección Bluetooth del PC recordado, o null si todavía no se eligió ninguno. */
    var pcDireccion: String?
        get() = prefs.getString("pc_direccion", null)
        set(valor) = prefs.edit().putString("pc_direccion", valor).apply()

    var pcNombre: String?
        get() = prefs.getString("pc_nombre", null)
        set(valor) = prefs.edit().putString("pc_nombre", valor).apply()

    fun olvidarPc() {
        prefs.edit().remove("pc_direccion").remove("pc_nombre").apply()
    }
}
