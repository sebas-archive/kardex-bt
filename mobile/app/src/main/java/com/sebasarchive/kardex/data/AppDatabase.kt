package com.sebasarchive.kardex.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [LecturaEntity::class, TareaEntity::class, ItemTareaEntity::class, InicioEntity::class, ProductoEntity::class,
        FotoEntity::class],
    version = 4,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun outbox(): Outbox
    abstract fun catalogo(): CatalogDao
    abstract fun fotos(): FotoDao

    companion object {
        @Volatile private var instancia: AppDatabase? = null

        /**
         * Versión 2: se quitó la ubicación. Las lecturas guardadas se conservan (con su `seq` y su estado, que es lo
         * que el PC usa para reanudar); solo se descarta la columna. SQLite viejo no sabe borrar columnas: se copia
         * la tabla.
         */
        val MIGRACION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    "CREATE TABLE lecturas_nueva (seq INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, tsOriginalMs INTEGER NOT NULL, " +
                        "idConteo TEXT NOT NULL, sku TEXT NOT NULL, cantidad TEXT NOT NULL, operador TEXT NOT NULL, " +
                        "nota TEXT NOT NULL, estado TEXT NOT NULL)"
                )
                db.execSQL(
                    "INSERT INTO lecturas_nueva (seq, tsOriginalMs, idConteo, sku, cantidad, operador, nota, estado) " +
                        "SELECT seq, tsOriginalMs, idConteo, sku, cantidad, operador, nota, estado FROM lecturas"
                )
                db.execSQL("DROP TABLE lecturas")
                db.execSQL("ALTER TABLE lecturas_nueva RENAME TO lecturas")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_lecturas_idConteo_sku ON lecturas (idConteo, sku)")
                db.execSQL("DROP TABLE IF EXISTS ubicaciones")
            }
        }

        /**
         * Versión 3 (Fase 3): los conteos pasan a ser tareas asignadas, con sus productos, y el teléfono recuerda
         * cuáles empezó el operador. El catálogo viejo se descarta (vuelve en la próxima sincronización); las
         * lecturas no se tocan.
         */
        val MIGRACION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("DROP TABLE IF EXISTS conteos")
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS tareas (id TEXT NOT NULL, nombre TEXT NOT NULL, almacen TEXT NOT NULL, " +
                        "instrucciones TEXT NOT NULL, estado TEXT NOT NULL, total INTEGER NOT NULL, contados INTEGER NOT NULL, " +
                        "PRIMARY KEY(id))"
                )
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS items_tarea (idTarea TEXT NOT NULL, sku TEXT NOT NULL, " +
                        "recuento INTEGER NOT NULL, PRIMARY KEY(idTarea, sku))"
                )
                db.execSQL("CREATE TABLE IF NOT EXISTS inicios (idTarea TEXT NOT NULL, PRIMARY KEY(idTarea))")
            }
        }

        /** Versión 4 (Fase 4): dañados en cada lectura y la cola de fotos de evidencia. Nada se pierde. */
        val MIGRACION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE lecturas ADD COLUMN danados TEXT NOT NULL DEFAULT ''")
                db.execSQL("CREATE TABLE IF NOT EXISTS fotos (seq INTEGER NOT NULL, archivo TEXT NOT NULL, " +
                    "estado TEXT NOT NULL, PRIMARY KEY(seq))")
            }
        }

        /** La base del teléfono (una sola instancia por proceso). */
        fun abrir(context: Context): AppDatabase = instancia ?: synchronized(this) {
            instancia ?: Room.databaseBuilder(context.applicationContext, AppDatabase::class.java, "inventario.db")
                .addMigrations(MIGRACION_1_2, MIGRACION_2_3, MIGRACION_3_4)
                .build()
                .also { instancia = it }
        }
    }
}
