package com.sebasarchive.kardex.ui

import android.content.Intent
import com.sebasarchive.kardex.ui.pantallas.LecturaFila
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** Corregir desde «Contado» abre Contar con lo que ya tenía la lectura: también los dañados (revisión final, I-3). */
@RunWith(RobolectricTestRunner::class)
class CorreccionTest {
    @Test
    fun corregir_conserva_cantidad_nota_y_danados() {
        val fila = LecturaFila("7701234000001", "Arroz", "10", "PENDIENTE", "caja rota", danados = "2")
        val ui = ContarActivity.uiInicial("T-01", ContarActivity.correccion(Intent(), fila))
        assertTrue(ui.edicion)
        assertEquals(listOf("10", "caja rota", "2"), listOf(ui.cantidad, ui.nota, ui.danados))
    }

    @Test
    fun contar_nuevo_empieza_vacio() {
        val ui = ContarActivity.uiInicial("T-01", Intent())
        assertEquals(listOf(false, "", "", ""), listOf(ui.edicion, ui.cantidad, ui.nota, ui.danados))
    }
}
