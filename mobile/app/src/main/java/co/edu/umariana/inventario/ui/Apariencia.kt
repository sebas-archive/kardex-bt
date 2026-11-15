package co.edu.umariana.inventario.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/**
 * Apariencia de la sesión: tema e idioma. Se cargan de [SettingsStore] al abrir cada pantalla, se cambian desde
 * «Mi cuenta» y se aplican de inmediato porque son estado de Compose.
 */
object Apariencia {
    var tema by mutableStateOf(SettingsStore.TEMA_SISTEMA)
    var idioma by mutableStateOf("es")

    /** Usuario con el que se están guardando las preferencias; null = invitado (Acceso y Estado de cuenta). */
    var usuarioActual: String? = null

    fun cargar(settings: SettingsStore, usuario: String?) {
        usuarioActual = usuario
        tema = settings.tema(usuario).takeIf { it in SettingsStore.TEMAS } ?: SettingsStore.TEMA_SISTEMA
        idioma = if (settings.idioma(usuario) == "en") "en" else "es"
    }

    fun cambiarTema(settings: SettingsStore, usuario: String?, valor: String) {
        if (valor !in SettingsStore.TEMAS) return
        tema = valor
        settings.guardarTema(usuario, valor)
    }

    fun cambiarIdioma(settings: SettingsStore, usuario: String?, valor: String) {
        idioma = if (valor == "en") "en" else "es"
        settings.guardarIdioma(usuario, idioma)
    }
}
