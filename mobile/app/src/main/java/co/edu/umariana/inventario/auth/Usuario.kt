package co.edu.umariana.inventario.auth

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Update
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

/** En el teléfono solo trabaja el Operador de Inventario: cuenta, escanea y sincroniza con el PC. */
object Rol {
    const val OPERADOR = "OPERADOR"

    fun nombre(rol: String): String = if (rol == OPERADOR) "Operador de Inventario" else rol
}

/**
 * Estado de la cuenta, el mismo que guarda Oracle. Una cuenta nueva queda PENDIENTE hasta que el administrador la
 * aprueba en el PC; el teléfono se entera al sincronizar (mensaje `ACCTST`). Solo una cuenta ACTIVO trabaja.
 */
object EstadoCuenta {
    const val PENDIENTE = "PENDIENTE"
    const val ACTIVO = "ACTIVO"
    const val RECHAZADO = "RECHAZADO"
    const val SUSPENDIDO = "SUSPENDIDO"
    val TODOS = listOf(PENDIENTE, ACTIVO, RECHAZADO, SUSPENDIDO)
}

/** Una cuenta del teléfono. `claveHash` y `respuestaHash` vienen de [Claves]: nunca texto plano. */
@Entity(tableName = "usuarios", indices = [Index(value = ["usuario"], unique = true)])
data class UsuarioEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val usuario: String,
    val nombre: String,
    val rol: String,
    val claveHash: String,
    val pregunta: String,
    val respuestaHash: String,
    val intentosFallidos: Int = 0,
    val bloqueadoHastaMs: Long = 0,
    val creadoMs: Long,
    val estado: String = EstadoCuenta.PENDIENTE,
    /** Por qué la rechazaron o suspendieron (lo escribió el administrador en el PC). */
    val motivo: String? = null,
)

@Dao
interface UsuarioDao {
    @Insert fun insertar(usuario: UsuarioEntity): Long
    @Update fun actualizar(usuario: UsuarioEntity)
    @Query("SELECT * FROM usuarios WHERE usuario = :usuario") fun porUsuario(usuario: String): UsuarioEntity?
    @Query("SELECT * FROM usuarios ORDER BY id") fun todos(): List<UsuarioEntity>
}

/**
 * Las cuentas viven en su propia base (`cuentas.db`), aparte de `inventario.db`: así añadirlas no obliga a migrar
 * la base donde están las lecturas pendientes de un teléfono que ya tenía la app.
 */
@Database(entities = [UsuarioEntity::class], version = 2, exportSchema = false)
abstract class CuentasDatabase : RoomDatabase() {
    abstract fun usuarios(): UsuarioDao

    companion object {
        /** Versión 2: estado y motivo de la cuenta; los clasificadores y supervisores pasan a operadores PENDIENTES. */
        val MIGRACION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE usuarios ADD COLUMN estado TEXT NOT NULL DEFAULT '${EstadoCuenta.PENDIENTE}'")
                db.execSQL("ALTER TABLE usuarios ADD COLUMN motivo TEXT")
                db.execSQL("UPDATE usuarios SET rol = '${Rol.OPERADOR}'")
            }
        }

        @Volatile private var instancia: CuentasDatabase? = null
        fun abrir(context: Context): CuentasDatabase = instancia ?: synchronized(this) {
            instancia ?: Room.databaseBuilder(context.applicationContext, CuentasDatabase::class.java, "cuentas.db")
                .addMigrations(MIGRACION_1_2)
                .build().also { instancia = it }
        }
    }
}
