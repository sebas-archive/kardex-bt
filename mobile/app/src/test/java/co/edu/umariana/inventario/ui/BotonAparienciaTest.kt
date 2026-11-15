package co.edu.umariana.inventario.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import co.edu.umariana.inventario.ui.componentes.BotonApariencia
import co.edu.umariana.inventario.ui.theme.InventarioTheme
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** El botón de apariencia debe abrir el diálogo y guardar tema/idioma del usuario en curso. */
@RunWith(RobolectricTestRunner::class)
class BotonAparienciaTest {
    @get:Rule
    val compose = createComposeRule()

    private val settings = SettingsStore(ApplicationProvider.getApplicationContext())

    @Before
    fun invitado() {
        settings.guardarTema(null, SettingsStore.TEMA_SISTEMA)
        settings.guardarIdioma(null, "es")
        Apariencia.cargar(settings, null)
    }

    @After
    fun limpiar() {
        settings.guardarTema(null, SettingsStore.TEMA_SISTEMA)
        settings.guardarIdioma(null, "es")
        Apariencia.cargar(settings, null)
    }

    @Test
    fun cambiaTemaEIdiomaYLosGuardaEnInvitado() {
        compose.setContent { InventarioTheme { BotonApariencia() } }
        compose.onNodeWithContentDescription("Apariencia").performClick()
        compose.onNodeWithText("Apariencia").assertIsDisplayed()

        compose.onNodeWithText("Oscuro").performClick()
        assertEquals(SettingsStore.TEMA_OSCURO, Apariencia.tema)
        assertEquals(SettingsStore.TEMA_OSCURO, settings.tema(null))
        compose.onNodeWithText("Apariencia").assertDoesNotExist()  // se cierra al elegir

        compose.onNodeWithContentDescription("Apariencia").performClick()
        compose.onNodeWithText("English").performClick()
        assertEquals("en", Apariencia.idioma)
        assertEquals("en", settings.idioma(null))
        compose.onNodeWithContentDescription("Appearance").assertIsDisplayed()
    }

    @Test
    fun elIdiomaCambiaLosTextosDelDialogoDeInmediato() {
        compose.setContent { InventarioTheme { BotonApariencia() } }
        compose.onNodeWithContentDescription("Apariencia").performClick()
        compose.onNodeWithText("Español").assertIsDisplayed()
        compose.onNodeWithText("English").performClick()
        compose.onNodeWithContentDescription("Appearance").assertIsDisplayed()
        compose.onNodeWithContentDescription("Appearance").performClick()
        compose.onNodeWithText("Theme").assertIsDisplayed()
        compose.onNodeWithText("Language").assertIsDisplayed()
        compose.onNodeWithText("Light").assertIsDisplayed()
        compose.onNodeWithText("Cancel").performClick()
    }
}
