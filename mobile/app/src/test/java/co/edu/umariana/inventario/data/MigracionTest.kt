package co.edu.umariana.inventario.data

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** Quitar la ubicación cambia la base del teléfono (versión 1 → 2): las lecturas guardadas no se pueden perder. */
@RunWith(RobolectricTestRunner::class)
class MigracionTest {
    @Test
    fun test_upgrade_from_v1_keeps_readings_with_their_seq_and_state() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val archivo = context.getDatabasePath("migracion.db").apply { parentFile?.mkdirs() }
        // La base tal como la creó la versión 1 de la app (con ubicación y la tabla de ubicaciones).
        SQLiteDatabase.openOrCreateDatabase(archivo, null).use { v1 ->
            v1.execSQL("CREATE TABLE lecturas (seq INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, tsOriginalMs INTEGER NOT NULL, " +
                "idConteo TEXT NOT NULL, ubicacion TEXT NOT NULL, sku TEXT NOT NULL, cantidad TEXT NOT NULL, " +
                "operador TEXT NOT NULL, nota TEXT NOT NULL, estado TEXT NOT NULL)")
            v1.execSQL("CREATE INDEX index_lecturas_idConteo_ubicacion_sku ON lecturas (idConteo, ubicacion, sku)")
            v1.execSQL("CREATE TABLE conteos (id TEXT NOT NULL, nombre TEXT NOT NULL, PRIMARY KEY(id))")
            v1.execSQL("CREATE TABLE ubicaciones (cod TEXT NOT NULL, zona TEXT NOT NULL, descripcion TEXT NOT NULL, PRIMARY KEY(cod))")
            v1.execSQL("CREATE TABLE productos (sku TEXT NOT NULL, nombre TEXT NOT NULL, categoria TEXT NOT NULL, unidad TEXT NOT NULL, PRIMARY KEY(sku))")
            v1.execSQL("INSERT INTO conteos VALUES ('T-01', 'Conteo de prueba')")
            v1.execSQL("INSERT INTO ubicaciones VALUES ('U1', 'Z1', 'Estante 1')")
            v1.execSQL("INSERT INTO lecturas VALUES (1, 1000, 'T-01', 'U1', 'A1', '5', 'Ana', '', 'CONFIRMADO')")
            v1.execSQL("INSERT INTO lecturas VALUES (2, 2000, 'T-01', 'U1', 'A2', '7.5', 'Ana', 'caja rota', 'PENDIENTE')")
            v1.version = 1
        }

        val db = Room.databaseBuilder(context, AppDatabase::class.java, "migracion.db")
            .addMigrations(AppDatabase.MIGRACION_1_2, AppDatabase.MIGRACION_2_3, AppDatabase.MIGRACION_3_4, AppDatabase.MIGRACION_4_5).allowMainThreadQueries().build()
        try {
            val lecturas = db.outbox().todas()  // abrirla valida el esquema nuevo: si la migración lo dejara distinto, falla aquí
            assertEquals(listOf(1L, 2L), lecturas.map { it.seq })
            assertEquals(listOf(Estado.CONFIRMADO, Estado.PENDIENTE), lecturas.map { it.estado })
            assertEquals(LecturaEntity(2, 2000, "ACTUAL", "A2", "7.5", "Ana", "caja rota", Estado.PENDIENTE), lecturas[1])  // danados = ""
            assertEquals(3L, db.outbox().insertar(LecturaEntity(tsOriginalMs = 3000, idConteo = "T-01", sku = "A3", cantidad = "1", operador = "Ana", nota = "")))
            assertEquals(emptyList<String>(), db.catalogo().productos().map { it.sku })   // el catálogo vuelve en la próxima sincronización
            assertEquals(0, db.notificaciones().noLeidas())                               // versión 5: tabla de avisos
        } finally {
            db.close()
        }
    }

    /** Fase 3 (versión 2 → 3): los conteos pasan a ser tareas. Las lecturas pendientes no se tocan. */
    @Test
    fun deV2aV3ConservaLasLecturasPendientes() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val archivo = context.getDatabasePath("migracion3.db").apply { parentFile?.mkdirs(); delete() }
        SQLiteDatabase.openOrCreateDatabase(archivo, null).use { v2 ->
            v2.execSQL("CREATE TABLE lecturas (seq INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, tsOriginalMs INTEGER NOT NULL, " +
                "idConteo TEXT NOT NULL, sku TEXT NOT NULL, cantidad TEXT NOT NULL, operador TEXT NOT NULL, " +
                "nota TEXT NOT NULL, estado TEXT NOT NULL)")
            v2.execSQL("CREATE INDEX index_lecturas_idConteo_sku ON lecturas (idConteo, sku)")
            v2.execSQL("CREATE TABLE conteos (id TEXT NOT NULL, nombre TEXT NOT NULL, PRIMARY KEY(id))")
            v2.execSQL("CREATE TABLE productos (sku TEXT NOT NULL, nombre TEXT NOT NULL, categoria TEXT NOT NULL, unidad TEXT NOT NULL, PRIMARY KEY(sku))")
            v2.execSQL("INSERT INTO conteos VALUES ('CONT-2026-11', 'Inventario')")
            v2.execSQL("INSERT INTO productos VALUES ('A1', 'Producto A1', 'Abarrotes', 'UND')")
            v2.execSQL("INSERT INTO lecturas VALUES (7, 1000, 'CONT-2026-11', 'A1', '5', 'Ana', 'caja rota', 'PENDIENTE')")
            v2.version = 2
        }

        val db = Room.databaseBuilder(context, AppDatabase::class.java, "migracion3.db")
            .addMigrations(AppDatabase.MIGRACION_1_2, AppDatabase.MIGRACION_2_3, AppDatabase.MIGRACION_3_4, AppDatabase.MIGRACION_4_5).allowMainThreadQueries().build()
        try {
            assertEquals(listOf(LecturaEntity(7, 1000, "ACTUAL", "A1", "5", "Ana", "caja rota", Estado.PENDIENTE)),
                db.outbox().todas())
            assertEquals(0, db.fotos().contarPendientes())   // versión 4: la tabla de fotos existe y está vacía
            assertEquals(listOf("A1"), db.catalogo().productos().map { it.sku })
            assertEquals(0, db.notificaciones().noLeidas())
        } finally {
            db.close()
        }
    }
}
