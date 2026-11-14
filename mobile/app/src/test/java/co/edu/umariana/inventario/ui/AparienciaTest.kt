package co.edu.umariana.inventario.ui

import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** Tema e idioma: se guardan por usuario y se recuperan al volver a abrir la app. */
@RunWith(RobolectricTestRunner::class)
class AparienciaTest {
    private val settings = SettingsStore(ApplicationProvider.getApplicationContext())

    @After
    fun limpiar() {
        Apariencia.cambiarTema(settings, "ana", SettingsStore.TEMA_SISTEMA)
        Apariencia.cambiarIdioma(settings, "ana", "es")
        Apariencia.cambiarTema(settings, "luis", SettingsStore.TEMA_SISTEMA)
        Apariencia.cambiarIdioma(settings, "luis", "es")
    }

    @Test
    fun cadaUsuarioTieneSuTemaYSuIdioma() {
        Apariencia.cargar(settings, "ana")
        assertEquals(SettingsStore.TEMA_SISTEMA, Apariencia.tema)
        assertEquals("es", Apariencia.idioma)

        Apariencia.cambiarTema(settings, "ana", SettingsStore.TEMA_OSCURO)
        Apariencia.cambiarIdioma(settings, "ana", "en")

        Apariencia.cargar(settings, "luis")  // otro operador en el mismo teléfono
        assertEquals(SettingsStore.TEMA_SISTEMA, Apariencia.tema)
        assertEquals("es", Apariencia.idioma)

        Apariencia.cargar(settings, "ana")   // la app se cerró y se volvió a abrir
        assertEquals(SettingsStore.TEMA_OSCURO, Apariencia.tema)
        assertEquals("en", Apariencia.idioma)
        assertEquals(SettingsStore.TEMA_OSCURO, settings.tema("ana"))
        assertEquals("en", settings.idioma("ana"))
    }
}
