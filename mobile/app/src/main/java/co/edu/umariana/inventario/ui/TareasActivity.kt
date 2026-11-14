package co.edu.umariana.inventario.ui

import android.os.Bundle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import co.edu.umariana.inventario.ui.pantallas.TareaFila
import co.edu.umariana.inventario.ui.pantallas.TareasScreen
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** «Mis tareas», a partir del catálogo que mandó el PC. Iniciar una la elige y abre «Contar». */
class TareasActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private var tareas by mutableStateOf<List<TareaFila>?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pantalla {
            val lista = tareas ?: return@pantalla  // hasta que carga, solo el fondo
            TareasScreen(
                lista, s.contar.conteo.value,
                alIniciar = { id ->
                    lifecycleScope.launch {
                        withContext(Dispatchers.IO) { s.contar.iniciarTarea(id) }
                        abrir(ContarActivity::class.java)
                        finish()
                    }
                },
                alVolver = { finish() },
                alSincronizar = { abrir(SincronizarActivity::class.java, Transicion.HOJA) },
            )
        }
    }

    override fun onResume() {
        super.onResume()  // al volver de sincronizar, pueden haber llegado tareas nuevas
        lifecycleScope.launch {
            tareas = withContext(Dispatchers.IO) {
                val iniciadas = s.contar.iniciadas()
                s.contar.tareas().map { t -> TareaFila(t, t.id in iniciadas, s.contar.items(t.id).count { it.recuento }) }
            }
        }
    }
}
