package com.sebasarchive.kardex.ui

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Test

class TextosTest {
    @After
    fun volverAEspanol() {
        Apariencia.idioma = "es"
    }

    @Test
    fun traduceLasEtiquetasYLasPlantillas() {
        Apariencia.idioma = "es"
        assertEquals("Entrar", Textos.t("Entrar"))
        assertEquals("3 lecturas por enviar", Textos.t("{n} lecturas por enviar", "n" to 3))
        Apariencia.idioma = "en"
        assertEquals("Sign in", Textos.t("Entrar"))
        assertEquals("Catalog", Textos.t("Catálogo"))
        assertEquals("3 readings to send", Textos.t("{n} lecturas por enviar", "n" to 3))
        assertEquals("reading to send", Textos.n(1, "lectura por enviar", "lecturas por enviar"))
    }
}
