package co.edu.umariana.inventario.sync

import co.edu.umariana.inventario.data.AppDatabase
import co.edu.umariana.inventario.data.Catalog
import co.edu.umariana.inventario.data.CatalogRepository
import co.edu.umariana.inventario.data.ConteoEntity
import co.edu.umariana.inventario.data.Estado
import co.edu.umariana.inventario.data.LecturaEntity
import co.edu.umariana.inventario.data.Outbox
import co.edu.umariana.inventario.data.ProductoEntity
import co.edu.umariana.inventario.data.TestDb
import co.edu.umariana.inventario.data.UbicacionEntity
import co.edu.umariana.inventario.protocol.Message
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

private const val S = FakePc.SERVER_NOW
private const val ADELANTO = 600_000L  // el reloj del teléfono va 10 minutos adelantado

@RunWith(RobolectricTestRunner::class)
class SyncClientTest {
    private lateinit var db: AppDatabase
    private lateinit var outbox: Outbox
    private lateinit var catalog: CatalogRepository
    private var phoneNow = S

    @Before
    fun abrir() {
        db = TestDb.abrir()
        outbox = db.outbox()
        catalog = CatalogRepository(db.catalogo())
    }

    @After
    fun cerrar() = db.close()

    private fun lectura(ts: Long, cantidad: String = "1") = LecturaEntity(
        tsOriginalMs = ts, idConteo = "T-01", ubicacion = "U1", sku = "A1",
        cantidad = cantidad, operador = "Ana", nota = "")

    private fun cargar(n: Int) = (1..n).forEach { outbox.insertar(lectura(ts = 1000L + it, cantidad = it.toString())) }

    private fun sync(pc: FakePc): List<SyncProgress> {
        val client = SyncClient(outbox, catalog, "dev-test-1", "Teléfono de prueba") { phoneNow }
        val eventos = runBlocking { client.sync(pc.connect()).toList() }
        pc.join()
        return eventos
    }

    private fun estados() = outbox.todas().map { it.estado }

    @Test
    fun test_sends_in_windows_of_50_and_marks_confirmed() {
        cargar(120)
        val pc = FakePc(stallBeforeAck = true)  // no confirma nada hasta que el teléfono se detiene
        val eventos = sync(pc)

        assertEquals(listOf(50, 50, 20), pc.bursts.toList())  // nunca más de 50 sin confirmar
        assertEquals((1L..120L).toList(), pc.accepted.map { it.seq })
        assertEquals((1..120).map { it.toString() }, pc.accepted.map { it.cantidad })
        assertEquals(Message("HELLO", listOf("1", "dev-test-1", "Teléfono de prueba")), pc.hello)
        assertTrue(estados().all { it == Estado.CONFIRMADO })
        assertEquals(SyncProgress.Connected(ultimoSeqServidor = 0, porEnviar = 120), eventos.first())
        assertEquals(listOf(25L, 50L, 75L, 100L, 120L),
            eventos.filterIsInstance<SyncProgress.Progress>().map { it.confirmadoHasta })
        assertEquals(SyncProgress.Done(aceptados = 120, rechazados = 0, pendientes = 0), eventos.last())
    }

    @Test
    fun test_go_back_n_on_nak_resends_from_expected_seq() {
        cargar(60)
        val pc = FakePc(nakOnce = mapOf(3L to "CRC"))  // el seq 3 "llega corrupto" la primera vez
        val eventos = sync(pc)

        // Envió 1..50, recibió NAK|3, retrocedió a 3 y reenvió 3..50; después, el resto.
        assertEquals((1L..50L) + (3L..50L) + (51L..60L), pc.received.map { it.seq })
        assertEquals((1L..60L).toList(), pc.accepted.map { it.seq })  // sin huecos ni duplicados
        assertTrue(estados().all { it == Estado.CONFIRMADO })
        assertEquals(SyncProgress.Done(aceptados = 60, rechazados = 1, pendientes = 0), eventos.last())
    }

    @Test
    fun test_resumes_from_ready_seq_after_cut() {
        cargar(40)
        val primero = sync(FakePc(cutAfterRecs = 30))  // el PC confirmó 25 y se cortó
        assertTrue("terminó con ${primero.last()}", primero.last() is SyncProgress.Cut)
        assertTrue(outbox.todas().filter { it.estado == Estado.CONFIRMADO }.all { it.seq <= 25 })
        assertTrue(outbox.todas().filter { it.seq > 25 }.none { it.estado == Estado.CONFIRMADO })

        val pc = FakePc(lastSeq = 25)  // al reconectar el PC dice hasta dónde tiene
        val segundo = sync(pc)
        assertEquals(SyncProgress.Connected(ultimoSeqServidor = 25, porEnviar = 15), segundo.first())
        assertEquals((26L..40L).toList(), pc.received.map { it.seq })  // ni uno repetido
        assertTrue(estados().all { it == Estado.CONFIRMADO })
        assertEquals(SyncProgress.Done(aceptados = 15, rechazados = 0, pendientes = 0), segundo.last())
    }

    @Test
    fun test_timestamps_use_server_offset() {
        val originales = listOf(S + ADELANTO - 5_000, S + ADELANTO - 3_000, S + ADELANTO - 1_000)
        originales.forEach { outbox.insertar(lectura(ts = it)) }
        phoneNow = S + ADELANTO
        val pc = FakePc(serverNowMs = S)
        sync(pc)

        assertEquals(listOf(S - 5_000, S - 3_000, S - 1_000), pc.accepted.map { it.tsMs })  // en hora del servidor
        assertEquals(originales, outbox.todas().map { it.tsOriginalMs })                      // la fila no cambia
    }

    @Test
    fun test_retry_does_not_apply_offset_twice() {
        val originales = listOf(S + ADELANTO - 5_000, S + ADELANTO - 3_000, S + ADELANTO - 1_000)
        originales.forEach { outbox.insertar(lectura(ts = it)) }
        phoneNow = S + ADELANTO
        val primero = sync(FakePc(serverNowMs = S, cutAfterRecs = 1))
        assertTrue("terminó con ${primero.last()}", primero.last() is SyncProgress.Cut)
        assertEquals(originales, outbox.todas().map { it.tsOriginalMs })

        // Un minuto después: el desfase se recalcula sobre la hora original, no se acumula.
        phoneNow = S + 60_000 + ADELANTO
        val pc = FakePc(serverNowMs = S + 60_000)
        sync(pc)
        assertEquals(listOf(S - 5_000, S - 3_000, S - 1_000), pc.accepted.map { it.tsMs })  // no S - 605 000
        assertEquals(originales, outbox.todas().map { it.tsOriginalMs })
        assertTrue(estados().all { it == Estado.CONFIRMADO })
    }

    @Test
    fun test_busy_nak_ends_with_busy() {
        cargar(3)
        val eventos = sync(FakePc(busy = true))
        assertEquals(listOf<SyncProgress>(SyncProgress.Busy), eventos)
        assertTrue(estados().all { it == Estado.PENDIENTE })  // nada salió: se reintenta después
    }

    @Test
    fun test_catalog_sent_by_the_pc_replaces_the_local_one() {
        catalog.reemplazarTodo(Catalog(
            conteos = listOf(ConteoEntity("VIEJO", "Conteo anterior")),
            ubicaciones = listOf(UbicacionEntity("X9", "ZX", "ya no existe")),
            productos = listOf(ProductoEntity("SKU-VIEJO", "Descontinuado", "Otros", "UND"))))

        val eventos = sync(FakePc())  // sin lecturas pendientes: solo baja el catálogo

        assertEquals(listOf("T-01"), catalog.conteos().map { it.id })
        assertEquals(listOf("U1", "U2"), catalog.ubicaciones().map { it.cod })
        assertEquals(listOf("A1", "A2"), catalog.productos().map { it.sku })
        assertEquals(ProductoEntity("A2", "Café | molido", "Abarrotes", "UND"), catalog.producto("A2"))
        assertNull(catalog.producto("SKU-VIEJO"))
        assertEquals(SyncProgress.Done(aceptados = 0, rechazados = 0, pendientes = 0), eventos.last())
    }
}
