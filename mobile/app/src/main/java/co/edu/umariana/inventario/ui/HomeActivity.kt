package co.edu.umariana.inventario.ui

import android.os.Bundle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import co.edu.umariana.inventario.auth.Rol
import co.edu.umariana.inventario.ui.pantallas.HomeScreen
import co.edu.umariana.inventario.ui.pantallas.HomeUi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Inicio: dónde está contando el operario y a dónde ir. Sin sesión abierta, manda al acceso. */
class HomeActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private var ui by mutableStateOf(HomeUi())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val abierta = s.auth.sesion()
        if (abierta == null || !abierta.puedeTrabajar) {  // sin sesión, al acceso; sin cuenta activa, a su estado
            reemplazarPor(if (abierta == null) AuthActivity::class.java else EstadoCuentaActivity::class.java)
            return
        }
        pantalla {
            HomeScreen(
                ui,
                alContar = {
                    when {
                        s.contar.conteo.value == null -> abrir(TareasActivity::class.java)
                        else -> abrir(ContarActivity::class.java)
                    }
                },
                alElegir = { abrir(TareasActivity::class.java) },
                alLecturas = { abrir(LecturasActivity::class.java) },
                alPendientes = { abrir(PendientesActivity::class.java) },
                alSincronizar = { abrir(SincronizarActivity::class.java, Transicion.HOJA) },
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
            // Tras sincronizar: si la tarea actual se cerró o se reasignó, ya no se cuenta en ella.
            val soltada = withContext(Dispatchers.IO) { if (hayCatalogo) s.contar.soltarTareaSiYaNoEsta() else null }
            if (soltada != null) {
                android.widget.Toast.makeText(this@HomeActivity, "La tarea $soltada ya no está asignada a ti.",
                    android.widget.Toast.LENGTH_LONG).show()
            }
            ui = HomeUi(sesion.nombre, Rol.nombre(sesion.rol), s.contar.conteo.value, pendientes, total, hayCatalogo, fotos)
        }
    }
}
