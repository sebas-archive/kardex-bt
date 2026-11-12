package com.sebasarchive.kardex.data

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Transaction

/** Estados de una lectura en la bandeja de salida. */
object Estado {
    const val PENDIENTE = "PENDIENTE"    // capturada, nunca enviada: todavía se puede recontar en sitio
    const val ENVIADO = "ENVIADO"        // salió hacia el PC y aún no hay confirmación
    const val CONFIRMADO = "CONFIRMADO"  // el PC la tiene guardada (ACK o READY)
}

/**
 * Una lectura capturada. `seq` es el número de secuencia del protocolo: lo asigna SQLite
 * (AUTOINCREMENT) y, como las filas nunca se borran, es contiguo desde 1.
 *
 * `tsOriginalMs` es la hora del reloj del teléfono al capturar y **no se modifica al sincronizar**:
 * el desfase con el servidor se suma solo en lo que se envía (D15).
 */
@Entity(tableName = "lecturas", indices = [Index(value = ["idConteo", "ubicacion", "sku"])])
data class LecturaEntity(
    @PrimaryKey(autoGenerate = true) val seq: Long = 0,
    val tsOriginalMs: Long,
    val idConteo: String,
    val ubicacion: String,
    val sku: String,
    val cantidad: String,
    val operador: String,
    val nota: String,
    val estado: String = Estado.PENDIENTE,
)

/** Bandeja de salida: todo se guarda aquí primero y de aquí sale hacia el PC. */
@Dao
abstract class Outbox {
    @Insert
    abstract fun insertar(lectura: LecturaEntity): Long

    /** Lo que falta por confirmar con `seq` ≥ [seq], en orden. */
    @Query("SELECT * FROM lecturas WHERE seq >= :seq AND estado != 'CONFIRMADO' ORDER BY seq")
    abstract fun pendientesDesde(seq: Long): List<LecturaEntity>

    /** ACK acumulativo: todo `seq` ≤ [seq] queda confirmado. Un ACK viejo no desconfirma nada. */
    @Query("UPDATE lecturas SET estado = 'CONFIRMADO' WHERE seq <= :seq AND estado != 'CONFIRMADO'")
    abstract fun confirmarHasta(seq: Long): Int

    @Query("SELECT COUNT(*) FROM lecturas WHERE estado != 'CONFIRMADO'")
    abstract fun contarPendientes(): Int

    @Query("SELECT COALESCE(MAX(seq), 0) FROM lecturas")
    abstract fun ultimoSeq(): Long

    @Query("SELECT * FROM lecturas ORDER BY seq")
    abstract fun todas(): List<LecturaEntity>

    @Query("SELECT * FROM lecturas WHERE seq = :seq")
    protected abstract fun porSeq(seq: Long): LecturaEntity?

    @Query("UPDATE lecturas SET estado = 'ENVIADO' WHERE seq = :seq AND estado = 'PENDIENTE'")
    protected abstract fun marcarEnviada(seq: Long): Int

    @Query("UPDATE lecturas SET estado = 'PENDIENTE' WHERE seq > :seq AND estado = 'ENVIADO'")
    protected abstract fun devolverEnviadasDespuesDe(seq: Long): Int

    @Query(
        "SELECT * FROM lecturas WHERE idConteo = :idConteo AND ubicacion = :ubicacion AND sku = :sku " +
            "AND estado = 'PENDIENTE' ORDER BY seq DESC LIMIT 1"
    )
    protected abstract fun pendienteDe(idConteo: String, ubicacion: String, sku: String): LecturaEntity?

    @Query("UPDATE lecturas SET cantidad = :cantidad, tsOriginalMs = :tsOriginalMs WHERE seq = :seq AND estado = 'PENDIENTE'")
    protected abstract fun actualizarPendiente(seq: Long, cantidad: String, tsOriginalMs: Long): Int

    /**
     * Lee la lectura [seq] y la marca ENVIADO en la misma transacción: lo que devuelve es
     * exactamente lo que va al PC, aunque alguien esté recontando a la vez.
     */
    @Transaction
    open fun tomarParaEnviar(seq: Long): LecturaEntity? {
        val lectura = porSeq(seq) ?: return null
        marcarEnviada(seq)
        return lectura
    }

    /**
     * Recontar: si la lectura de esa ubicación y SKU **nunca se envió**, se corrige en sitio (con la
     * hora del recuento) y devuelve true. Si ya salió hacia el PC no se toca —el PC puede tenerla— y
     * devuelve false: quien llama inserta una lectura nueva y el servidor se queda con la más reciente (D13).
     */
    @Transaction
    open fun reemplazar(idConteo: String, ubicacion: String, sku: String, cantidad: String, tsOriginalMs: Long): Boolean {
        val pendiente = pendienteDe(idConteo, ubicacion, sku) ?: return false
        return actualizarPendiente(pendiente.seq, cantidad, tsOriginalMs) == 1
    }

    /**
     * Al conectar, el PC dice cuál es el último `seq` que tiene guardado ([ultimoSeqServidor]):
     * hasta ahí queda confirmado y lo enviado después (que se perdió en un corte) vuelve a PENDIENTE.
     */
    @Transaction
    open fun reconciliar(ultimoSeqServidor: Long) {
        confirmarHasta(ultimoSeqServidor)
        devolverEnviadasDespuesDe(ultimoSeqServidor)
    }
}
