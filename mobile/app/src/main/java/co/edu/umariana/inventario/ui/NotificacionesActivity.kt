package co.edu.umariana.inventario.ui

import android.os.Bundle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import co.edu.umariana.inventario.data.NotificacionEntity
import co.edu.umariana.inventario.data.PantallaAviso
import co.edu.umariana.inventario.ui.pantallas.NotificacionesScreen
import co.edu.umariana.inventario.ui.pantallas.NotificacionesUi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Notificaciones: todas o sin leer, marcar todas y abrir la pantalla relacionada. */
class NotificacionesActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private var ui by mutableStateOf(NotificacionesUi())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pantalla {
            NotificacionesScreen(
                ui,
                alCambiarFiltro = { ui = ui.copy(soloSinLeer = it) },
                alMarcarTodas = {
                    lifecycleScope.launch {
                        withContext(Dispatchers.IO) { s.notificaciones.marcarTodas() }
                        cargar()
                    }
                },
                alAbrir = { aviso ->
                    lifecycleScope.launch {
                        withContext(Dispatchers.IO) { s.notificaciones.marcar(aviso.id) }
                        cargar()
                        abrir(aviso)
                    }
                },
                alVolver = { finish() },
            )
        }
    }

    override fun onResume() {
        super.onResume()
        cargar()
    }

    private fun cargar() {
        lifecycleScope.launch {
            ui = ui.copy(avisos = withContext(Dispatchers.IO) { s.notificaciones.todas() })
        }
    }

    private fun abrir(aviso: NotificacionEntity) {
        when (aviso.pantalla) {
            PantallaAviso.CATALOGO -> abrir(CatalogoActivity::class.java)
            PantallaAviso.CONTAR -> abrir(ContarActivity::class.java)
            PantallaAviso.CONTADO -> abrir(LecturasActivity::class.java)
            PantallaAviso.PENDIENTES -> abrir(PendientesActivity::class.java)
            PantallaAviso.SINCRONIZAR -> abrir(SincronizarActivity::class.java, Transicion.HOJA)
            PantallaAviso.MI_CUENTA -> abrir(PerfilActivity::class.java, Transicion.HOJA)
            PantallaAviso.ESTADO_CUENTA -> abrir(EstadoCuentaActivity::class.java)
            else -> abrir(HomeActivity::class.java)
        }
    }
}
