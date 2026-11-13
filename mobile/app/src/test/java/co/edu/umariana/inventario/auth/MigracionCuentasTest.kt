package co.edu.umariana.inventario.auth

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** Cuentas de estado (versión 1 → 2): los clasificadores y supervisores pasan a operadores PENDIENTES de aprobación. */
@RunWith(RobolectricTestRunner::class)
class MigracionCuentasTest {
    @Test
    fun migracionDeRolesLlevaClasificadorYSupervisorAOperador() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val archivo = context.getDatabasePath("cuentas-migracion.db").apply { parentFile?.mkdirs(); delete() }
        SQLiteDatabase.openOrCreateDatabase(archivo, null).use { v1 ->
            v1.execSQL("CREATE TABLE usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, usuario TEXT NOT NULL, " +
                "nombre TEXT NOT NULL, rol TEXT NOT NULL, claveHash TEXT NOT NULL, pregunta TEXT NOT NULL, " +
                "respuestaHash TEXT NOT NULL, intentosFallidos INTEGER NOT NULL, bloqueadoHastaMs INTEGER NOT NULL, creadoMs INTEGER NOT NULL)")
            v1.execSQL("CREATE UNIQUE INDEX index_usuarios_usuario ON usuarios (usuario)")
            v1.execSQL("INSERT INTO usuarios VALUES (1, 'ana', 'Ana', 'CLASIFICADOR', 'h', 'p', 'r', 0, 0, 1000)")
            v1.execSQL("INSERT INTO usuarios VALUES (2, 'luis', 'Luis', 'SUPERVISOR', 'h', 'p', 'r', 0, 0, 2000)")
            v1.version = 1
        }

        val db = Room.databaseBuilder(context, CuentasDatabase::class.java, "cuentas-migracion.db")
            .addMigrations(CuentasDatabase.MIGRACION_1_2).allowMainThreadQueries().build()
        try {
            val cuentas = db.usuarios().todos()   // abrirla valida el esquema nuevo
            assertEquals(listOf(Rol.OPERADOR, Rol.OPERADOR), cuentas.map { it.rol })
            assertEquals(listOf(EstadoCuenta.PENDIENTE, EstadoCuenta.PENDIENTE), cuentas.map { it.estado })
            assertEquals(listOf(null, null), cuentas.map { it.motivo })
        } finally {
            db.close()
        }
    }
}
