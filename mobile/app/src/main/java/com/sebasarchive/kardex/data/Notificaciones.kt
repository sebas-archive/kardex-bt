package com.sebasarchive.kardex.data

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query

/**
 * Avisos del sistema. Se guardan como **tipo + dato**, no como texto: así el idioma se aplica al mostrarlos y
 * cambiar de idioma también traduce los avisos viejos. [pantalla] dice a qué pantalla lleva tocarlo.
 */
@Entity(tableName = "notificaciones")
data class NotificacionEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val tipo: String,
    /** Dato del aviso: un número (lecturas, productos) o el motivo del PC. */
    val dato: String = "",
    val pantalla: String? = null,
    val leida: Boolean = false,
    val creadoMs: Long,
)

/** Tipos de aviso; el texto vive en la tabla de traducciones de la interfaz. */
object TipoAviso {
    const val CUENTA_CREADA = "CUENTA_CREADA"
    const val CUENTA_ACTIVA = "CUENTA_ACTIVA"
    const val CUENTA_PENDIENTE = "CUENTA_PENDIENTE"
    const val CUENTA_SUSPENDIDA = "CUENTA_SUSPENDIDA"
    const val CUENTA_RECHAZADA = "CUENTA_RECHAZADA"
    const val CLAVE_RESTABLECIDA = "CLAVE_RESTABLECIDA"
    const val SYNC_OK = "SYNC_OK"
    const val SYNC_CON_PENDIENTES = "SYNC_CON_PENDIENTES"
    const val SYNC_SIN_CONEXION = "SYNC_SIN_CONEXION"
    const val CATALOGO_ACTUALIZADO = "CATALOGO_ACTUALIZADO"
}

/** Pantallas a las que puede llevar una notificación. */
object PantallaAviso {
    const val INICIO = "INICIO"
    const val CATALOGO = "CATALOGO"
    const val CONTAR = "CONTAR"
    const val CONTADO = "CONTADO"
    const val PENDIENTES = "PENDIENTES"
    const val SINCRONIZAR = "SINCRONIZAR"
    const val MI_CUENTA = "MI_CUENTA"
    const val ESTADO_CUENTA = "ESTADO_CUENTA"
}

@Dao
interface NotificacionDao {
    @Insert fun insertar(notificacion: NotificacionEntity): Long
    @Query("SELECT * FROM notificaciones ORDER BY creadoMs DESC, id DESC") fun todas(): List<NotificacionEntity>
    @Query("SELECT COUNT(*) FROM notificaciones WHERE leida = 0") fun noLeidas(): Int
    @Query("UPDATE notificaciones SET leida = 1 WHERE leida = 0") fun marcarTodas()
    @Query("UPDATE notificaciones SET leida = 1 WHERE id = :id") fun marcar(id: Long)
}

/** Avisos locales: se generan al crear la cuenta, al restablecer la clave y al terminar una sincronización. */
class NotificacionRepository(private val dao: NotificacionDao, private val ahoraMs: () -> Long = System::currentTimeMillis) {
    fun crear(tipo: String, dato: String = "", pantalla: String? = null): NotificacionEntity {
        val aviso = NotificacionEntity(tipo = tipo, dato = dato, pantalla = pantalla, creadoMs = ahoraMs())
        dao.insertar(aviso)
        return aviso
    }

    fun todas(): List<NotificacionEntity> = dao.todas()
    fun noLeidas(): Int = dao.noLeidas()
    fun marcarTodas() = dao.marcarTodas()
    fun marcar(id: Long) = dao.marcar(id)
}
