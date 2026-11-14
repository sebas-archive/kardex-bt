package com.sebasarchive.kardex.sync

import com.sebasarchive.kardex.data.AppDatabase
import com.sebasarchive.kardex.data.Catalog
import com.sebasarchive.kardex.data.CatalogRepository
import com.sebasarchive.kardex.data.FotoEntity
import com.sebasarchive.kardex.data.FotoRepository
import com.sebasarchive.kardex.data.Estado
import com.sebasarchive.kardex.data.LecturaEntity
import com.sebasarchive.kardex.data.Outbox
import com.sebasarchive.kardex.data.ProductoEntity
import com.sebasarchive.kardex.data.TestDb
import com.sebasarchive.kardex.protocol.EstadoCuentaPc
import com.sebasarchive.kardex.protocol.Message
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertArrayEquals
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
    private lateinit var fotos: FotoRepository
    @get:org.junit.Rule val carpeta = org.junit.rules.TemporaryFolder()
    private var phoneNow = S
    private val estadosCuenta = ArrayList<EstadoCuentaPc>()

    @Before
    fun abrir() {
        db = TestDb.abrir()
        outbox = db.outbox()
        catalog = CatalogRepository(db.catalogo())
        fotos = FotoRepository(db.fotos(), carpeta.newFolder("fotos"))
    }

    @After
    fun cerrar() = db.close()

    private fun lectura(ts: Long, cantidad: String = "1") = LecturaEntity(
        tsOriginalMs = ts, idConteo = "ACTUAL", sku = "A1",
        cantidad = cantidad, operador = "Ana", nota = "")

    private fun cargar(n: Int) = (1..n).forEach { outbox.insertar(lectura(ts = 1000L + it, cantidad = it.toString())) }

    private fun sync(pc: FakePc): List<SyncProgress> {
        val client = SyncClient(outbox, catalog, "dev-test-1", "Teléfono de prueba", "ana.gomez", "Ana Gómez",
            alEstado = { estadosCuenta += it }, fotos = fotos) { phoneNow }
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
        assertEquals(Message("HELLO", listOf("5", "dev-test-1", "Teléfono de prueba")), pc.hello)
        assertEquals(Message("ACCT", listOf("ana.gomez", "Ana Gómez")), pc.acct)
        assertEquals(listOf(EstadoCuentaPc("ana.gomez", "ACTIVO", "OPERADOR", null)), estadosCuenta)
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
        catalog.reemplazarTodo(Catalog(productos = listOf(ProductoEntity("SKU-VIEJO", "Descontinuado", "Otros", "UND"))))

        val eventos = sync(FakePc())  // sin lecturas pendientes: solo baja el catálogo

        assertEquals(listOf("A1", "A2"), catalog.productos().map { it.sku })
        assertEquals(ProductoEntity("A2", "Café | molido", "Abarrotes", "UND"), catalog.producto("A2"))
        assertNull(catalog.producto("SKU-VIEJO"))
        assertEquals(SyncProgress.Done(aceptados = 0, rechazados = 0, pendientes = 0), eventos.last())
    }

    @Test
    fun elCatalogoPseudoCatalogoNoEnviaInicio() {
        cargar(1)
        val pc = FakePc()
        sync(pc)
        assertTrue(pc.inicios.isEmpty())
        assertEquals(listOf("REC", "END"), pc.recibidos)
        assertEquals("ACTUAL", pc.accepted.single().idConteo)
    }

    @Test
    fun conCuentaSuspendidaNoEnviaRegistrosYLosConserva() {
        cargar(5)
        val pc = FakePc(estadoCuenta = "SUSPENDIDO", motivoCuenta = "Vacaciones | hasta el lunes")
        val eventos = sync(pc)
        assertTrue(pc.received.isEmpty())                       // ni un REC salió del teléfono
        assertTrue(estados().all { it == Estado.PENDIENTE })    // siguen en el búfer para cuando la reactiven
        assertEquals(listOf(EstadoCuentaPc("ana.gomez", "SUSPENDIDO", null, "Vacaciones | hasta el lunes")), estadosCuenta)
        assertEquals(SyncProgress.CuentaNoActiva("SUSPENDIDO", "Vacaciones | hasta el lunes", pendientes = 5), eventos.last())
    }

    @Test
    fun conCuentaActivaEnviaRegistros() {
        cargar(3)
        val pc = FakePc()
        val eventos = sync(pc)
        assertEquals(listOf(1L, 2L, 3L), pc.accepted.map { it.seq })
        assertEquals(SyncProgress.Done(aceptados = 3, rechazados = 0, pendientes = 0), eventos.last())
    }



    // ------------------------------------------------------------------ fotos (protocolo 5)
    private fun foto(seq: Long, bytes: Int = 10_000): ByteArray {
        val datos = ByteArray(bytes) { (it * 7 + seq).toByte() }
        val temporal = carpeta.newFile().apply { writeBytes(datos) }
        fotos.adjuntar(seq, temporal)
        return datos
    }

    private fun estadoFoto(seq: Long) = db.fotos().porSeq(seq)!!.estado

    @Test
    fun lasFotosSalenDespuesDeLasLecturasYQuedanEnviadas() {
        cargar(3)
        val datos = foto(2)
        val pc = FakePc()
        val eventos = sync(pc)
        assertArrayEquals(datos, pc.fotos[2L])
        assertEquals(FotoEntity.ENVIADA, estadoFoto(2))
        assertEquals(listOf("REC", "REC", "REC", "FOTO", "FOTO", "FOTO", "FOTO", "FOTO", "END"), pc.recibidos)
        assertEquals(SyncProgress.Done(aceptados = 3, rechazados = 0, pendientes = 0), eventos.last())
        assertEquals(0, fotos.contarPendientes())
    }

    @Test
    fun fotoGrandeQuedaRechazadaYConCrcMaloSeReintenta() {
        cargar(2)
        foto(1)
        foto(2)
        sync(FakePc(fotoErr = mapOf(1L to "GRANDE", 2L to "CRC")))
        assertEquals(FotoEntity.RECHAZADA, estadoFoto(1))
        assertEquals(FotoEntity.PENDIENTE, estadoFoto(2))
        assertEquals(1, fotos.contarPendientes())
    }

    @Test(timeout = 20_000)
    fun unNakEnLaUltimaParteDeUnaFotoNoCuelgaLaSincronizacion() {
        cargar(2)
        foto(2)
        val eventos = sync(FakePc(nakFotoFinal = 2))
        assertEquals(FotoEntity.PENDIENTE, estadoFoto(2))       // se reintenta en la próxima sesión
        assertTrue(estados().all { it == Estado.CONFIRMADO })
        assertTrue(eventos.last() is SyncProgress.Done)
    }

    @Test
    fun corteAMitadDeUnaFotoLaDejaPendienteYLasLecturasConfirmadas() {
        cargar(2)
        foto(2)
        sync(FakePc(cutOnFotoPart = 3))
        assertEquals(FotoEntity.PENDIENTE, estadoFoto(2))
        assertTrue(estados().all { it == Estado.CONFIRMADO })   // la primera parte ya hizo confirmar las lecturas
    }

    @Test
    fun fotoDeUnaLecturaDeOtraSesionSaleSola() {
        cargar(2)
        sync(FakePc())                       // las lecturas ya están en el PC
        val datos = foto(1, bytes = 500)     // y luego se adjunta la foto (p. ej. no se pudo enviar antes)
        val pc = FakePc(lastSeq = 2)
        sync(pc)
        assertArrayEquals(datos, pc.fotos[1L])
        assertEquals(listOf("FOTO", "END"), pc.recibidos)
    }

    @Test
    fun conCuentaSuspendidaNoSalenFotos() {
        cargar(1)
        sync(FakePc())
        foto(1)
        val pc = FakePc(estadoCuenta = "SUSPENDIDO", lastSeq = 1)
        sync(pc)
        assertTrue(pc.fotos.isEmpty())
        assertEquals(FotoEntity.PENDIENTE, estadoFoto(1))
    }
}
