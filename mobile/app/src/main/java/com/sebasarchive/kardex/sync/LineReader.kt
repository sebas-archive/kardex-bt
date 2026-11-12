package com.sebasarchive.kardex.sync

import java.io.ByteArrayOutputStream
import java.io.InputStream

/**
 * Lee líneas terminadas en `\n` de un flujo de bytes. Conserva lo ya leído si la lectura se
 * interrumpe (p. ej. por un timeout del socket), así que se puede volver a llamar sin perder datos.
 */
class LineReader(private val input: InputStream, private val maxLineBytes: Int = 65_536) {
    private val pending = ByteArrayOutputStream()
    private val chunk = ByteArray(4096)
    private var length = 0
    private var position = 0

    /** La siguiente línea sin su `\n`, o `null` si el otro lado cerró. */
    fun readLine(): ByteArray? {
        while (true) {
            while (position < length) {
                val b = chunk[position++]
                if (b == NEWLINE) {
                    val line = pending.toByteArray()
                    pending.reset()
                    return line
                }
                // Una línea desmesurada se trunca: no pasará la validación del protocolo.
                if (pending.size() < maxLineBytes) pending.write(b.toInt())
            }
            val read = input.read(chunk)
            if (read < 0) return null
            length = read
            position = 0
        }
    }

    private companion object {
        const val NEWLINE = '\n'.code.toByte()
    }
}
