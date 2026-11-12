package co.edu.umariana.inventario

import android.content.Context
import java.util.UUID

/**
 * Identidad del dispositivo ante el PC (D18): un UUID que se genera en el primer uso y se guarda
 * en el almacenamiento privado de la app. Reinstalar o borrar los datos crea una identidad nueva,
 * con `seq` desde 1 (por eso el manifiesto lleva `allowBackup="false"`).
 */
object DeviceIdentity {
    const val PREFS = "identidad"
    const val KEY = "uuid_instalacion"

    @Synchronized
    fun get(context: Context): String {
        val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.getString(KEY, null)?.let { return it }
        val nuevo = UUID.randomUUID().toString()
        prefs.edit().putString(KEY, nuevo).commit()  // en disco antes de usarlo: es la clave de la idempotencia
        return nuevo
    }
}
