package co.edu.umariana.inventario.data

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class OutboxTest {
    private lateinit var db: AppDatabase
    private lateinit var outbox: Outbox

    @Before
    fun abrir() {
        db = TestDb.abrir()
        outbox = db.outbox()
    }

    @After
    fun cerrar() = db.close()

    private fun lectura(sku: String = "A1", cantidad: String = "1", ts: Long = 1000, conteo: String = "T-01") =
        LecturaEntity(tsOriginalMs = ts, idConteo = conteo, sku = sku,
            cantidad = cantidad, operador = "Ana", nota = "")

    @Test
    fun test_confirmarHasta_marks_all_leq_seq() {
        val seqs = (1..5).map { outbox.insertar(lectura(sku = "A$it")) }
        assertEquals(listOf(1L, 2L, 3L, 4L, 5L), seqs)  // contiguos desde 1: lo exige el protocolo

        outbox.confirmarHasta(3)
        assertEquals(
            listOf(Estado.CONFIRMADO, Estado.CONFIRMADO, Estado.CONFIRMADO, Estado.PENDIENTE, Estado.PENDIENTE),
            outbox.todas().map { it.estado })
        assertEquals(listOf(4L, 5L), outbox.pendientesDesde(1).map { it.seq })
        assertEquals(listOf(5L), outbox.pendientesDesde(5).map { it.seq })
        assertEquals(2, outbox.contarPendientes())

        outbox.confirmarHasta(2)  // un ACK viejo no desconfirma nada
        assertEquals(listOf(4L, 5L), outbox.pendientesDesde(1).map { it.seq })
    }

    @Test
    fun test_reemplazar_updates_existing_reading_for_same_sku() {
        val seq = outbox.insertar(lectura(sku = "A1", cantidad = "40", ts = 1000))
        outbox.insertar(lectura(sku = "A1", cantidad = "7", ts = 1100, conteo = "T-02"))  // otro conteo
        outbox.insertar(lectura(sku = "A2", cantidad = "9", ts = 1200))  // otro SKU

        assertTrue(outbox.reemplazar("T-01", "A1", "45", 2000))

        val todas = outbox.todas()
        assertEquals(3, todas.size)  // recontar no agrega fila
        val recontada = todas.first { it.seq == seq }
        assertEquals("45", recontada.cantidad)
        assertEquals(2000L, recontada.tsOriginalMs)  // la hora de captura es la del recuento (D13)
        assertEquals(Estado.PENDIENTE, recontada.estado)
        assertEquals(listOf("7", "9"), todas.filter { it.seq != seq }.map { it.cantidad })

        assertFalse(outbox.reemplazar("T-01", "A9", "1", 3000))  // no había lectura: quien llama inserta
        assertEquals(3, outbox.todas().size)
    }

    @Test
    fun test_reemplazar_never_touches_a_reading_already_sent() {
        val seq = outbox.insertar(lectura(cantidad = "40"))
        assertEquals("40", outbox.tomarParaEnviar(seq)!!.cantidad)  // ya salió hacia el PC
        assertEquals(Estado.ENVIADO, outbox.todas().single().estado)

        assertFalse(outbox.reemplazar("T-01", "A1", "45", 2000))  // el PC puede tener el 40: no se pisa
        assertEquals("40", outbox.todas().single().cantidad)
        outbox.confirmarHasta(seq)
        assertFalse(outbox.reemplazar("T-01", "A1", "45", 2000))
        assertEquals("40", outbox.todas().single().cantidad)

        // Tras un corte el PC dice qué tiene: lo enviado que no llegó vuelve a PENDIENTE.
        val otra = outbox.insertar(lectura(sku = "A2", cantidad = "5"))
        outbox.tomarParaEnviar(otra)
        outbox.reconciliar(seq)
        assertEquals(listOf(Estado.CONFIRMADO, Estado.PENDIENTE), outbox.todas().map { it.estado })
        assertTrue(outbox.reemplazar("T-01", "A2", "6", 3000))
    }
}
