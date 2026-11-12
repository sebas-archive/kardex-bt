package co.edu.umariana.inventario.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [LecturaEntity::class, ConteoEntity::class, UbicacionEntity::class, ProductoEntity::class],
    version = 1,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun outbox(): Outbox
    abstract fun catalogo(): CatalogDao

    companion object {
        @Volatile private var instancia: AppDatabase? = null

        /** La base del teléfono (una sola instancia por proceso). */
        fun abrir(context: Context): AppDatabase = instancia ?: synchronized(this) {
            instancia ?: Room.databaseBuilder(context.applicationContext, AppDatabase::class.java, "inventario.db")
                .build()
                .also { instancia = it }
        }
    }
}
