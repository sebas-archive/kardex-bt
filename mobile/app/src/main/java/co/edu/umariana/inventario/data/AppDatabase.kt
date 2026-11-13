package co.edu.umariana.inventario.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [LecturaEntity::class, ConteoEntity::class, ProductoEntity::class],
    version = 2,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun outbox(): Outbox
    abstract fun catalogo(): CatalogDao

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

        /** La base del teléfono (una sola instancia por proceso). */
        fun abrir(context: Context): AppDatabase = instancia ?: synchronized(this) {
            instancia ?: Room.databaseBuilder(context.applicationContext, AppDatabase::class.java, "inventario.db")
                .addMigrations(MIGRACION_1_2)
                .build()
                .also { instancia = it }
        }
    }
}
