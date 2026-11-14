package com.sebasarchive.kardex.ui

import android.os.Bundle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import com.sebasarchive.kardex.auth.AuthResult
import com.sebasarchive.kardex.auth.EstadoCuenta
import com.sebasarchive.kardex.data.PantallaAviso
import com.sebasarchive.kardex.data.TipoAviso
import com.sebasarchive.kardex.ui.pantallas.AuthScreen
import com.sebasarchive.kardex.ui.pantallas.AuthUi
import com.sebasarchive.kardex.ui.pantallas.ModoAuth
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Acceso: entrar, crear cuenta y recuperar la contraseña. Sin sesión abierta la app no pasa de aquí. */
class AuthActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private var ui by mutableStateOf(AuthUi())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pantalla {
            AuthScreen(
                ui,
                alCambiarModo = { if (!ui.cargando) ui = AuthUi(modo = it) },
                alEntrar = { usuario, clave -> intentar({ s.auth.iniciarSesion(usuario, clave) }, ::entrar) },
                alRegistrar = { d ->
                    intentar({ s.auth.registrar(d.usuario, d.nombre, d.clave, d.confirmacion, d.pregunta, d.respuesta, d.correo) }) { resultado ->
                        lifecycleScope.launch(Dispatchers.IO) {
                            s.notificaciones.crear(TipoAviso.CUENTA_CREADA, "", PantallaAviso.ESTADO_CUENTA)
                        }
                        entrar(resultado)
                    }
                },
                alBuscarPregunta = { usuario ->
                    if (!ui.cargando) lifecycleScope.launch {
                        ui = ui.copy(cargando = true, error = null)
                        val pregunta = withContext(Dispatchers.IO) { s.auth.preguntaDe(usuario) }
                        ui = if (pregunta != null) ui.copy(cargando = false, pregunta = pregunta)
                        else ui.copy(cargando = false, error = AuthResult.UsuarioNoExiste.mensaje(), sacudida = ui.sacudida + 1)
                    }
                },
                alRestablecer = { usuario, respuesta, clave, confirmacion ->
                    intentar({ s.auth.restablecer(usuario, respuesta, clave, confirmacion) }) {
                        lifecycleScope.launch(Dispatchers.IO) {
                            s.notificaciones.crear(TipoAviso.CLAVE_RESTABLECIDA, "", PantallaAviso.INICIO)
                        }
                        ui = AuthUi(modo = ModoAuth.ENTRAR, aviso = Textos.t("Contraseña restablecida. Entra con la nueva."))
                    }
                },
            )
        }
    }

    /** Corre [operacion] fuera del hilo de la interfaz (derivar la clave es lento a propósito) y muestra el error si falla. */
    private fun intentar(operacion: () -> AuthResult, alLograrlo: (AuthResult.Ok) -> Unit) {
        if (ui.cargando || ui.bienvenida != null) return
        lifecycleScope.launch {
            ui = ui.copy(cargando = true, error = null, aviso = null)
            val resultado = withContext(Dispatchers.IO) { operacion() }
            if (resultado is AuthResult.Ok) alLograrlo(resultado)
            else ui = ui.copy(cargando = false, error = resultado.mensaje(), sacudida = ui.sacudida + 1)
        }
    }

    private fun entrar(resultado: AuthResult.Ok) {
        s.contar.setOperador(resultado.usuario.nombre)  // el operador de cada lectura es quien tiene la sesión (D20)
        ui = ui.copy(cargando = false, bienvenida = resultado.usuario.nombre)
        val destino = if (resultado.usuario.estado == EstadoCuenta.ACTIVO) HomeActivity::class.java else EstadoCuentaActivity::class.java
        lifecycleScope.launch {
            delay(1_150)  // lo que dura el saludo
            reemplazarPor(destino)  // una cuenta pendiente, rechazada o suspendida solo ve su estado
        }
    }
}
