package com.sebasarchive.kardex.ui

import android.os.Bundle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import com.sebasarchive.kardex.ui.pantallas.EstadoCuentaScreen
import com.sebasarchive.kardex.ui.pantallas.EstadoCuentaUi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * La cuenta de la sesión no está ACTIVO. Desde aquí solo se puede comprobar el estado (sincronizando con el PC)
 * o salir. Al volver de sincronizar, si el administrador ya la activó, entra al inicio.
 */
class EstadoCuentaActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private var ui by mutableStateOf<EstadoCuentaUi?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pantalla {
            ui?.let {
                EstadoCuentaScreen(
                    it,
                    alComprobar = { abrir(SincronizarActivity::class.java, Transicion.HOJA) },
                    alSalir = {
                        s.auth.cerrarSesion()
                        reemplazarPor(AuthActivity::class.java)
                    },
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()
        val sesion = s.auth.sesion() ?: run { reemplazarPor(AuthActivity::class.java); return }
        if (sesion.puedeTrabajar) {  // el PC la aprobó o la reactivó mientras tanto
            reemplazarPor(HomeActivity::class.java)
            return
        }
        lifecycleScope.launch {
            val registrado = withContext(Dispatchers.IO) { s.auth.registradoMs(sesion.usuario) }
            ui = EstadoCuentaUi(sesion.nombre, sesion.usuario, sesion.estado, sesion.motivo, registrado)
        }
    }
}
