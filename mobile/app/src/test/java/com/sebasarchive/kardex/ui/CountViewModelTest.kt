package com.sebasarchive.kardex.ui

import androidx.test.core.app.ApplicationProvider
import com.sebasarchive.kardex.data.AppDatabase
import com.sebasarchive.kardex.data.Catalog
import com.sebasarchive.kardex.data.CatalogRepository
import com.sebasarchive.kardex.data.ConteoEntity
import com.sebasarchive.kardex.data.Estado
import com.sebasarchive.kardex.data.ProductoEntity
import com.sebasarchive.kardex.data.TestDb
import com.sebasarchive.kardex.data.UbicacionEntity
import com.sebasarchive.kardex.protocol.Protocol
import com.sebasarchive.kardex.protocol.Rec
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class CountViewModelTest {
    private lateinit var db: AppDatabase
    private lateinit var settings: SettingsStore
    private lateinit var vm: CountViewModel
    private var ahora = 1_731_170_400_000L

    private fun nuevoVm() = CountViewModel(db.outbox(), CatalogRepository(db.catalogo()), settings) { ahora }

    @Before
    fun abrir() {
        db = TestDb.abrir()
        settings = SettingsStore(ApplicationProvider.getApplicationContext())
        CatalogRepository(db.catalogo()).reemplazarTodo(
            Catalog(
                conteos = listOf(ConteoEntity("T-01", "Conteo de prueba")),
                ubicaciones = listOf(UbicacionEntity("U1", "Z1", "Estante 1"), UbicacionEntity("U2", "Z1", "Estante 2")),
                productos = listOf(ProductoEntity("A1", "Producto A1", "Abarrotes", "UND"),
                    ProductoEntity("A2", "Café | molido", "Abarrotes", "UND")),
            )
        )
        vm = nuevoVm()
    }

    @After
    fun cerrar() = db.close()

    /** Operador y conteo ya elegidos: lo que tiene el teléfono después de la configuración inicial. */
    private fun listo() {
        vm.setOperador("Ana")
        vm.elegirConteo("T-01")
    }

    @Test
    fun test_save_requires_operator_name() {
        vm.elegirConteo("T-01")
        assertEquals(SaveResult.OperadorFaltante, vm.guardar("U1", "A1", "5", ""))
        vm.setOperador("   ")  // en blanco no cuenta
        assertEquals(SaveResult.OperadorFaltante, vm.guardar("U1", "A1", "5", ""))
        assertTrue(db.outbox().todas().isEmpty())

        vm.setOperador("  Ana ")
        assertEquals("Ana", vm.operador.value)  // sin espacios sobrantes
        assertTrue(vm.guardar("U1", "A1", "5", "") is SaveResult.Guardada)
        assertEquals("Ana", db.outbox().todas().single().operador)
    }

    @Test
    fun test_operator_over_60_chars_is_rejected() {
        vm.elegirConteo("T-01")
        vm.setOperador("x".repeat(61))
        assertEquals("", vm.operador.value)
        assertEquals(SaveResult.OperadorFaltante, vm.guardar("U1", "A1", "5", ""))

        vm.setOperador("y".repeat(60))  // el límite es inclusivo
        assertEquals("y".repeat(60), vm.operador.value)
        vm.setOperador("z".repeat(61))  // uno inválido no pisa el operador vigente
        assertEquals("y".repeat(60), vm.operador.value)
    }

    @Test
    fun test_invalid_quantity_blocks_save() {
        listo()
        for (mala in listOf("1,5", "-1", "1.2345", "", " ", "abc", "1234567890", "1.", ".5", "1e3")) {
            assertEquals("«$mala» debía rechazarse", SaveResult.CantidadInvalida, vm.guardar("U1", "A1", mala, ""))
        }
        assertTrue(db.outbox().todas().isEmpty())
        for (buena in listOf("0", "7", "12.5", "0.001", "123456789", "123456789.123")) {
            assertTrue("«$buena» debía aceptarse", vm.guardar("U2", "A2", buena, "") is SaveResult.Guardada)
        }
    }

    @Test
    fun test_unknown_sku_warns_but_can_save() {
        listo()
        val conocido = vm.guardar("U1", "A1", "3", "") as SaveResult.Guardada
        assertFalse(conocido.skuDesconocido)

        val raro = vm.guardar("U1", "9999999999999", "2", "") as SaveResult.Guardada
        assertTrue(raro.skuDesconocido)  // advertencia, no error: el producto puede darse de alta después (D16)
        assertEquals(2, db.outbox().todas().size)
    }

    @Test
    fun test_recount_replaces_previous_in_same_location() {
        listo()
        val primera = vm.guardar("U1", "A1", "5", "") as SaveResult.Guardada
        assertFalse(primera.reemplazo)
        ahora += 60_000
        val segunda = vm.guardar("U1", "A1", "7", "") as SaveResult.Guardada
        assertTrue(segunda.reemplazo)
        assertEquals(primera.seq, segunda.seq)

        val filas = db.outbox().todas()
        assertEquals(1, filas.size)
        assertEquals("7", filas[0].cantidad)
        assertEquals(ahora, filas[0].tsOriginalMs)
        assertEquals("7", vm.ultimaLectura("U1", "A1")?.cantidad)

        // Otra ubicación suma aparte (D13): no es un recuento.
        assertFalse((vm.guardar("U2", "A1", "4", "") as SaveResult.Guardada).reemplazo)
        assertEquals(2, db.outbox().todas().size)
        assertNull(vm.ultimaLectura("U2", "A2"))
    }

    @Test
    fun test_recount_after_the_reading_was_sent_adds_a_new_row() {
        listo()
        val primera = vm.guardar("U1", "A1", "5", "") as SaveResult.Guardada
        db.outbox().tomarParaEnviar(primera.seq)  // ya salió hacia el PC: no se toca
        ahora += 60_000
        val segunda = vm.guardar("U1", "A1", "7", "") as SaveResult.Guardada
        assertFalse(segunda.reemplazo)
        assertEquals(listOf("5", "7"), db.outbox().todas().map { it.cantidad })
        assertEquals(listOf(Estado.ENVIADO, Estado.PENDIENTE), db.outbox().todas().map { it.estado })
        assertEquals("7", vm.ultimaLectura("U1", "A1")?.cantidad)  // el PC se queda con la más reciente
    }

    @Test
    fun test_note_over_255_chars_is_rejected() {
        listo()
        assertEquals(SaveResult.NotaLarga, vm.guardar("U1", "A1", "5", "n".repeat(256)))
        assertTrue(db.outbox().todas().isEmpty())
        assertTrue(vm.guardar("U1", "A1", "5", "n".repeat(255)) is SaveResult.Guardada)
    }

    @Test
    fun test_operator_and_note_with_pipe_and_newline_are_encoded_in_rec() {
        vm.elegirConteo("T-01")
        vm.setOperador("Ana|Luis")
        val nota = "caja rota | 2 pzs\nrevisar 100%"
        vm.guardar("U1", "A1", "5", nota)

        val fila = db.outbox().todas().single()
        assertEquals(nota, fila.nota)  // en la base va tal cual; se codifica al armar el REC
        val rec = Rec(fila.seq, fila.tsOriginalMs, fila.idConteo, fila.ubicacion, fila.sku, fila.cantidad, fila.operador, fila.nota)
        val cruda = rec.toRaw()
        assertEquals("el REC debe tener 9 campos", 9, cruda.split("|").size)
        assertTrue(cruda.contains("Ana%7CLuis"))
        assertTrue(cruda.contains("caja rota %7C 2 pzs%0Arevisar 100%25"))
        assertEquals(rec, Rec.fromMessage(Protocol.parse(rec.toFrame())))  // y llega idéntico
    }

    @Test
    fun test_operator_is_remembered_across_instances() {
        vm.setOperador("Ana")
        vm.elegirConteo("T-01")
        val otro = nuevoVm()  // la app se cerró y se volvió a abrir
        assertEquals("Ana", otro.operador.value)
        assertEquals("T-01", otro.conteo.value)
    }

    @Test
    fun test_missing_conteo_location_or_sku_blocks_save() {
        vm.setOperador("Ana")
        assertEquals(SaveResult.SinConteo, vm.guardar("U1", "A1", "5", ""))
        vm.elegirConteo("T-01")
        assertEquals(SaveResult.UbicacionFaltante, vm.guardar(" ", "A1", "5", ""))
        assertEquals(SaveResult.SkuFaltante, vm.guardar("U1", "  ", "5", ""))
        assertTrue(db.outbox().todas().isEmpty())
    }

    @Test
    fun test_location_list_shows_latest_reading_per_sku() {
        listo()
        vm.guardar("U1", "A1", "5", "")
        vm.guardar("U1", "A2", "3", "")
        vm.guardar("U2", "A1", "9", "")
        vm.guardar("U1", "A1", "6", "")  // recuento
        assertEquals(listOf("A1" to "6", "A2" to "3"), vm.lecturasDe("U1").map { it.sku to it.cantidad })
    }
}
