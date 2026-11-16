package com.sebasarchive.kardex.ui

import android.os.Bundle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import com.sebasarchive.kardex.auth.Rol
import com.sebasarchive.kardex.ui.pantallas.HomeScreen
import com.sebasarchive.kardex.ui.pantallas.HomeUi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Inicio: quién cuenta, cuánto falta por enviar y a dónde ir. Sin sesión: primero conectar con el PC y luego el acceso. */
class HomeActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private var ui by mutableStateOf(HomeUi())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val abierta = s.auth.sesion()
        if (abierta == null || !abierta.puedeTrabajar) {  // sin sesión, al acceso; sin cuenta activa, a su estado
            when {
                abierta != null -> reemplazarPor(EstadoCuentaActivity::class.java)
                !s.pcVerificado -> reemplazarPor(SincronizarActivity::class.java) { putExtra(SincronizarActivity.EXTRA_SOLO_CONECTAR, true) }
                else -> reemplazarPor(AuthActivity::class.java)
            }
            return
        }
        pantalla {
            HomeScreen(
                ui,
                alContar = { abrir(ContarActivity::class.java) },
                alCatalogo = { abrir(CatalogoActivity::class.java) },
                alLecturas = { abrir(LecturasActivity::class.java) },
                alPendientes = { abrir(PendientesActivity::class.java) },
                alSincronizar = { abrir(SincronizarActivity::class.java, Transicion.HOJA) },
                alNotificaciones = { abrir(NotificacionesActivity::class.java, Transicion.HOJA) },
                alPerfil = { abrir(PerfilActivity::class.java, Transicion.HOJA) },
            )
        }
    }

    override fun onResume() {
        super.onResume()
        val sesion = s.auth.sesion() ?: return
        if (!sesion.puedeTrabajar) {  // el PC la suspendió en la última sincronización
            reemplazarPor(EstadoCuentaActivity::class.java)
            return
        }
        if (s.contar.operador.value != sesion.nombre) s.contar.setOperador(sesion.nombre)  // el operador es quien tiene la sesión (D20)
        lifecycleScope.launch {
            val (pendientes, total, hayCatalogo) = withContext(Dispatchers.IO) {
                Triple(s.contar.contarPendientes(), s.contar.todasLasLecturas().size, s.contar.hayCatalogo())
            }
            val fotos = withContext(Dispatchers.IO) { s.contar.fotosPendientes() }
            val noLeidas = withContext(Dispatchers.IO) { s.notificaciones.noLeidas() }
            ui = HomeUi(sesion.nombre, Rol.nombre(sesion.rol), pendientes, total, hayCatalogo, fotos,
                sesion.foto, noLeidas)
        }
    }
}
