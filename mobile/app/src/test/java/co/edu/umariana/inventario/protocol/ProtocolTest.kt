package co.edu.umariana.inventario.protocol

import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.fail
import org.junit.Test
import java.io.File

/** El protocolo Kotlin contra los mismos vectores que Python (docs/protocol-vectors.json). */
class ProtocolTest {

    private fun vectors(): List<JSONObject> {
        var dir: File? = File(System.getProperty("user.dir")!!).absoluteFile
        while (dir != null && !File(dir, "docs/protocol-vectors.json").exists()) dir = dir.parentFile
        requireNotNull(dir) { "no se encontró docs/protocol-vectors.json subiendo desde ${System.getProperty("user.dir")}" }
        val array = JSONObject(File(dir, "docs/protocol-vectors.json").readText(Charsets.UTF_8)).getJSONArray("vectors")
        return (0 until array.length()).map { array.getJSONObject(it) }
    }

    private fun JSONObject.strings(key: String): List<String> =
        getJSONArray(key).let { a -> (0 until a.length()).map { a.getString(it) } }

    private fun vector(name: String): JSONObject = vectors().first { it.getString("name") == name }

    @Test
    fun test_frame_and_parse_match_all_shared_vectors() {
        val vectors = vectors()
        assertEquals(11, vectors.size)
        for (v in vectors) {
            val name = v.getString("name")
            val line = v.getString("line").toByteArray(Charsets.UTF_8)
            val withNewline = line + '\n'.code.toByte()
            assertArrayEquals(name, withNewline, Protocol.frame(v.strings("frame_fields")))
            val expected = Message(v.getString("kind"), v.strings("fields"))
            assertEquals(name, expected, Protocol.parse(withNewline))
            assertEquals(name, expected, Protocol.parse(line))  // el salto final es opcional al leer
        }
    }

    @Test
    fun acctYAcctstCoincidenConLosVectores() {
        assertEquals("3", Protocol.VERSION)
        val acct = vector("acct")
        assertArrayEquals((acct.getString("line") + "\n").toByteArray(Charsets.UTF_8),
            Protocol.frame(listOf("ACCT", Protocol.encodeText("luis.ortiz"), Protocol.encodeText("Luis Ortiz"))))
        val st = Protocol.parse(vector("acctst_suspendido").getString("line").toByteArray(Charsets.UTF_8))
        assertEquals(EstadoCuentaPc("luis.ortiz", "SUSPENDIDO", "OPERADOR", "Revisar | inventario al 100%\nhabla con el jefe"),
            EstadoCuentaPc.fromMessage(st))
        val pendiente = EstadoCuentaPc.fromMessage(Protocol.parse(vector("acctst_pendiente").getString("line").toByteArray(Charsets.UTF_8)))
        assertEquals(EstadoCuentaPc("luis.ortiz", "PENDIENTE", null, null), pendiente)  // vacíos → null
    }

    @Test
    fun test_text_with_separators_survives_the_wire() {
        val original = "a|b\nc%ñ😀\r"
        val encoded = Protocol.encodeText(original)
        assertFalse(encoded.contains('|') || encoded.contains('\n') || encoded.contains('\r'))
        assertEquals(original, Protocol.decodeText(encoded))
        assertEquals("%7C", Protocol.decodeText("%257C"))  // un %25 no se decodifica dos veces

        val line = vector("rec_special_text").getString("line")
        val rec = Rec.fromMessage(Protocol.parse(line.toByteArray(Charsets.UTF_8)))
        assertEquals(Rec(2, 1731170401000, "CONT-2026-11", "7701234000012", "3", "Ñandú|%", "a|b\nc%😀"), rec)
        assertEquals(line.substringBeforeLast('*'), rec.toRaw())
        assertArrayEquals((line + "\n").toByteArray(Charsets.UTF_8), rec.toFrame())
    }

    @Test
    fun test_invalid_lines_are_rejected_with_their_reason() {
        fun reason(line: ByteArray): String = try {
            Protocol.parse(line)
            fail("debió rechazar ${String(line.copyOf(minOf(line.size, 40)))}")
            ""
        } catch (e: FrameError) {
            e.reason
        }

        assertEquals("CRC", reason("ACK|3*6A8544FB".toByteArray()))            // último dígito cambiado
        assertEquals("FORMAT", reason("ACK|3".toByteArray()))                  // sin CRC
        assertEquals("FORMAT", reason("ACK|3*6a8544fa".toByteArray()))         // CRC en minúsculas
        assertEquals("FORMAT", reason(Protocol.frame(listOf("REC", "1", "2"))))  // CRC bueno, faltan campos
        assertEquals("FORMAT", reason(Protocol.frame(listOf("HOLA", "1"))))    // tipo desconocido
        val base = listOf("REC", "1", "2", "C", "U", "S", "1", "Ana")
        val overhead = Protocol.frame(base + "").size - 1
        assertEquals("REC", Protocol.parse(Protocol.frame(base + "x".repeat(4000 - overhead))).kind)  // 4000 bytes: válido
        assertEquals("LINEA_LARGA", reason(Protocol.frame(base + "x".repeat(4001 - overhead))))
    }
}
