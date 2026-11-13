package co.edu.umariana.inventario.ui

import co.edu.umariana.inventario.sync.BluetoothSocketLike
import co.edu.umariana.inventario.sync.SyncProgress
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream

/** Reintentos y mensajes de la pantalla Sincronizar, sin radio ni Android. */
class SyncRunnerTest {
    private class Socket : BluetoothSocketLike {
        override val inputStream: InputStream = ByteArrayInputStream(ByteArray(0))
        override val outputStream: OutputStream = ByteArrayOutputStream()
        override fun close() {}
    }

    private fun runner(
        conexiones: MutableList<Int>,
        falla: Boolean = false,
        intentos: List<List<SyncProgress>>,
    ): SyncRunner {
        var n = 0
        return SyncRunner(
            conectar = { intento ->
                conexiones += intento
                if (falla) throw IOException("sin servicio")
                Socket()
            },
            sincronizar = { _: BluetoothSocketLike -> flowOf(*intentos[minOf(n++, intentos.size - 1)].toTypedArray()) as Flow<SyncProgress> },
            maxIntentos = 3,
            pausaMs = 0,
        )
    }

    private fun estados(r: SyncRunner) = runBlocking { r.ejecutar().toList() }

    @Test
    fun test_done_without_pending_ends_ok() {
        val conexiones = mutableListOf<Int>()
        val s = estados(runner(conexiones, intentos = listOf(listOf(
            SyncProgress.Connected(0, 3), SyncProgress.Progress(3, 3), SyncProgress.Done(3, 0, 0)))))
        assertEquals(listOf(1), conexiones)
        assertEquals(SyncEstado.Conectando(1), s.first())
        assertTrue(s.contains(SyncEstado.Sincronizando(3, 3)))
        assertEquals(SyncEstado.Listo(3, 0, 0), s.last())
    }

    @Test
    fun test_cut_is_retried_and_then_completes() {
        val conexiones = mutableListOf<Int>()
        val s = estados(runner(conexiones, intentos = listOf(
            listOf(SyncProgress.Connected(0, 40), SyncProgress.Cut("link loss", 15)),
            listOf(SyncProgress.Connected(25, 15), SyncProgress.Done(15, 0, 0)))))
        assertEquals(listOf(1, 2), conexiones)
        assertTrue(s.any { it is SyncEstado.Reintentando && it.intento == 2 })
        assertEquals(SyncEstado.Listo(15, 0, 0), s.last())
    }

    @Test
    fun test_cut_on_every_attempt_ends_cut_with_pending_count() {
        val conexiones = mutableListOf<Int>()
        val s = estados(runner(conexiones, intentos = listOf(listOf(SyncProgress.Cut("link loss", 15)))))
        assertEquals(listOf(1, 2, 3), conexiones)
        assertEquals(SyncEstado.Cortado("link loss", 15), s.last())
    }

    @Test
    fun test_done_with_pending_syncs_again() {
        val conexiones = mutableListOf<Int>()
        val s = estados(runner(conexiones, intentos = listOf(
            listOf(SyncProgress.Done(50, 1, 10)),
            listOf(SyncProgress.Done(10, 0, 0)))))
        assertEquals(listOf(1, 2), conexiones)
        assertEquals(SyncEstado.Listo(10, 0, 0), s.last())
    }

    @Test
    fun test_busy_is_not_retried() {
        val conexiones = mutableListOf<Int>()
        val s = estados(runner(conexiones, intentos = listOf(listOf(SyncProgress.Busy))))
        assertEquals(listOf(1), conexiones)
        assertEquals(SyncEstado.Ocupado, s.last())
    }

    @Test
    fun cuentaNoActivaNoSeReintenta() {
        val conexiones = mutableListOf<Int>()
        val s = estados(runner(conexiones, intentos = listOf(listOf(SyncProgress.CuentaNoActiva("PENDIENTE", null, 4)))))
        assertEquals(listOf(1), conexiones)   // insistir no cambia nada: hay que esperar al administrador
        assertEquals(SyncEstado.CuentaNoActiva("PENDIENTE", null, 4), s.last())
    }

    @Test
    fun test_pc_unreachable_is_retried_then_reported() {
        val conexiones = mutableListOf<Int>()
        val s = estados(runner(conexiones, falla = true, intentos = listOf(emptyList())))
        assertEquals(listOf(1, 2, 3), conexiones)
        assertEquals(SyncEstado.PcNoDisponible("sin servicio"), s.last())
    }
}
