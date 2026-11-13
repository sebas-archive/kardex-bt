package co.edu.umariana.inventario.protocol

import java.nio.ByteBuffer
import java.nio.charset.CharacterCodingException
import java.nio.charset.CodingErrorAction
import java.util.Locale
import java.util.zip.CRC32

/**
 * Protocolo de líneas entre el móvil y el PC. Es el mismo de `server/btsync/protocol.py` y se
 * prueba contra los mismos vectores (`docs/protocol-vectors.json`); el formato está en `docs/protocolo.md`.
 *
 * Una línea por mensaje: `KIND|campo|campo...*CRC32` terminada en `\n`. El CRC32 (8 hex mayúsculas)
 * cubre los bytes UTF-8 anteriores al último `*`. Máximo 4000 bytes por línea, sin contar el `\n`.
 */

/** Línea inválida. [reason] es `CRC`, `FORMAT` o `LINEA_LARGA`. */
class FrameError(val reason: String, detail: String = "") :
    Exception(if (detail.isEmpty()) reason else "$reason: $detail")

/** Un mensaje ya validado; [fields] viene sin el tipo y con el texto libre decodificado. */
data class Message(val kind: String, val fields: List<String>)

/** Una lectura tal como viaja en un `REC`. */
data class Rec(
    val seq: Long,
    val tsMs: Long,
    val idConteo: String,
    val sku: String,
    val cantidad: String,
    val operador: String,
    val nota: String,
) {
    private fun wireFields(): List<String> =
        listOf("REC", seq.toString(), tsMs.toString()) +
            listOf(idConteo, sku, cantidad, operador, nota).map(Protocol::encodeText)

    /** La línea `REC` como va por el cable, sin el CRC. */
    fun toRaw(): String = wireFields().joinToString("|")

    /** La línea completa, con CRC y salto de línea. */
    fun toFrame(): ByteArray = Protocol.frame(wireFields())

    companion object {
        fun fromMessage(m: Message): Rec {
            if (m.kind != "REC" || m.fields.size != 7) throw FrameError("FORMAT", "REC exige exactamente 7 campos")
            val seq = m.fields[0].toLongOrNull() ?: throw FrameError("FORMAT", "seq debe ser entero")
            val ts = m.fields[1].toLongOrNull() ?: throw FrameError("FORMAT", "epoch_ms debe ser entero")
            return Rec(seq, ts, m.fields[2], m.fields[3], m.fields[4], m.fields[5], m.fields[6])
        }
    }
}

/** Lo que el PC responde en `ACCTST`: el estado de la cuenta del operador. Rol y motivo vacíos llegan como null. */
data class EstadoCuentaPc(val usuario: String, val estado: String, val rol: String?, val motivo: String?) {
    companion object {
        fun fromMessage(m: Message): EstadoCuentaPc {
            if (m.kind != "ACCTST" || m.fields.size < 4) throw FrameError("FORMAT", "ACCTST exige 4 campos")
            return EstadoCuentaPc(m.fields[0], m.fields[1], m.fields[2].ifEmpty { null }, m.fields[3].ifEmpty { null })
        }
    }
}

object Protocol {
    const val MAX_LINE_BYTES = 4000

    /**
     * Versión del protocolo que viaja en `HELLO`. La 2 quitó la ubicación del `REC` y el mensaje `CATUBIC`; la 3
     * añadió `ACCT`/`ACCTST` (la cuenta del operador y su estado).
     */
    const val VERSION = "3"

    // Cantidad mínima de partes (incluido el tipo) de cada mensaje.
    private val MIN_PARTS = mapOf(
        "HELLO" to 4, "ACCT" to 3, "ACCTST" to 5, "REC" to 8, "END" to 2,
        "READY" to 3, "CATCONTEO" to 3, "CATPROD" to 5, "CAT_END" to 1,
        "ACK" to 2, "NAK" to 3, "BYE" to 3,
    )
    private val ESCAPE = Regex("%(?:25|7C|0D|0A)")
    private val CRC_HEX = Regex("[0-9A-F]{8}")
    private const val NEWLINE = '\n'.code.toByte()
    private const val STAR = '*'.code.toByte()

    /** Texto libre → cable: `%`, `|`, CR y LF no pueden viajar tal cual. */
    fun encodeText(s: String): String =
        s.replace("%", "%25").replace("|", "%7C").replace("\r", "%0D").replace("\n", "%0A")

    /** Cable → texto libre, en una sola pasada (un `%25` no se decodifica dos veces). */
    fun decodeText(s: String): String = ESCAPE.replace(s) {
        when (it.value) {
            "%25" -> "%"
            "%7C" -> "|"
            "%0D" -> "\r"
            else -> "\n"
        }
    }

    /** Arma la línea. `fields[0]` es el tipo; el resto ya viene codificado. */
    fun frame(fields: List<String>): ByteArray {
        val body = fields.joinToString("|").toByteArray(Charsets.UTF_8)
        val crc = CRC32().apply { update(body) }.value
        return body + String.format(Locale.ROOT, "*%08X\n", crc).toByteArray(Charsets.US_ASCII)
    }

    /** Valida longitud, CRC y forma. El `\n` final es opcional. Lanza [FrameError]. */
    fun parse(line: ByteArray): Message {
        var end = line.size
        if (end > 0 && line[end - 1] == NEWLINE) end--
        if (end > MAX_LINE_BYTES) throw FrameError("LINEA_LARGA", "$end bytes")

        var star = end - 1
        while (star >= 0 && line[star] != STAR) star--
        if (star < 0 || end - star - 1 != 8) throw FrameError("FORMAT", "falta el CRC")
        val crcText = String(line, star + 1, 8, Charsets.ISO_8859_1)
        if (!CRC_HEX.matches(crcText)) throw FrameError("FORMAT", "CRC mal formado")
        val crc = CRC32().apply { update(line, 0, star) }.value
        if (crc != crcText.toLong(16)) throw FrameError("CRC")

        val text = try {
            Charsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(line, 0, star))
                .toString()
        } catch (e: CharacterCodingException) {
            throw FrameError("FORMAT", "UTF-8 inválido")
        }
        val parts = text.split("|")
        val minimum = MIN_PARTS[parts[0]] ?: throw FrameError("FORMAT", "tipo desconocido '${parts[0]}'")
        if (parts.size < minimum) throw FrameError("FORMAT", "${parts[0]} exige $minimum partes, llegaron ${parts.size}")
        return Message(parts[0], parts.drop(1).map(::decodeText))
    }
}
