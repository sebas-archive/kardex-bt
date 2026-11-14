package com.sebasarchive.kardex.data

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import java.io.File

/**
 * La foto de evidencia de una lectura ([seq]): un JPG comprimido en la carpeta de fotos de la app. Cola aparte de las
 * lecturas (protocolo 5): sale después de ellas, una a la vez. [estado]: PENDIENTE (por enviar), ENVIADA (el PC
 * respondió FOTOOK) o RECHAZADA (el PC la rechazó por grande: no se reintenta).
 */
@Entity(tableName = "fotos")
data class FotoEntity(@PrimaryKey val seq: Long, val archivo: String, val estado: String = PENDIENTE) {
    companion object {
        const val PENDIENTE = "PENDIENTE"
        const val ENVIADA = "ENVIADA"
        const val RECHAZADA = "RECHAZADA"
    }
}

@Dao
abstract class FotoDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) abstract fun guardar(foto: FotoEntity)
    @Query("SELECT * FROM fotos WHERE seq = :seq") abstract fun porSeq(seq: Long): FotoEntity?
    @Query("UPDATE fotos SET estado = :estado WHERE seq = :seq") abstract fun marcar(seq: Long, estado: String)
    @Query("SELECT COUNT(*) FROM fotos WHERE estado = 'PENDIENTE'") abstract fun contarPendientes(): Int
    @Query("SELECT seq FROM fotos") abstract fun conFoto(): List<Long>

    /** Fotos por enviar cuya lectura ya salió hacia el PC (en esta sesión o antes): el PC sabe a qué asociarlas. */
    @Query("SELECT f.* FROM fotos f JOIN lecturas l ON l.seq = f.seq WHERE f.estado = 'PENDIENTE' " +
        "AND l.estado != 'PENDIENTE' ORDER BY f.seq")
    abstract fun enviables(): List<FotoEntity>
}

/** Las fotos en disco ([dir]/<seq>.jpg) y su cola en Room. */
class FotoRepository(private val dao: FotoDao, val dir: File) {
    /** Adjunta (o reemplaza) la foto de la lectura [seq] moviendo [temporal] a su lugar. Queda por enviar. */
    fun adjuntar(seq: Long, temporal: File) {
        dir.mkdirs()
        val destino = File(dir, "$seq.jpg")
        if (!temporal.renameTo(destino)) {
            temporal.copyTo(destino, overwrite = true)
            temporal.delete()
        }
        dao.guardar(FotoEntity(seq, destino.name))
    }

    fun archivo(seq: Long): File? = dao.porSeq(seq)?.let { File(dir, it.archivo) }?.takeIf { it.exists() }
    fun enviables(): List<FotoEntity> = dao.enviables()
    fun marcar(seq: Long, estado: String) = dao.marcar(seq, estado)
    fun contarPendientes(): Int = dao.contarPendientes()
    fun conFoto(): Set<Long> = dao.conFoto().toSet()
}
