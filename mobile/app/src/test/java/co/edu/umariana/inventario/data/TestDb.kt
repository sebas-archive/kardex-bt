package co.edu.umariana.inventario.data

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider

object TestDb {
    /** Base Room en memoria (SQLite real, vía Robolectric). */
    fun abrir(): AppDatabase =
        Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext(), AppDatabase::class.java)
            .allowMainThreadQueries()
            .build()
}
