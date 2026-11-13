package com.sebasarchive.kardex.ui

import android.os.Bundle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import com.sebasarchive.kardex.auth.AuthResult
import com.sebasarchive.kardex.ui.pantallas.PerfilScreen
import com.sebasarchive.kardex.ui.pantallas.PerfilUi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Mi cuenta: datos de la sesión, cambio de contraseña y cierre de sesión. */
class PerfilActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private var ui by mutableStateOf(PerfilUi())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val sesion = s.auth.sesion() ?: run { reemplazarPor(AuthActivity::class.java); return }
        pantalla {
            PerfilScreen(
                sesion, ui,
                alAbrirCambio = { ui = PerfilUi(cambiando = it) },
                alCambiarClave = { actual, nueva, confirmacion ->
                    lifecycleScope.launch {
                        val resultado = withContext(Dispatchers.IO) { s.auth.cambiarClave(actual, nueva, confirmacion) }
                        ui = if (resultado is AuthResult.Ok) PerfilUi(aviso = "Contraseña cambiada.")
                        else ui.copy(error = if (resultado == AuthResult.CredencialesInvalidas) "La contraseña actual no es correcta" else resultado.mensaje())
                    }
                },
                alCerrarSesion = {
                    s.auth.cerrarSesion()
                    reemplazarPor(AuthActivity::class.java)
                },
                alVolver = { finish() },
            )
        }
    }
}
