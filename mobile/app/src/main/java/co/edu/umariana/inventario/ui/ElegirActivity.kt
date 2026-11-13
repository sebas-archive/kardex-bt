package co.edu.umariana.inventario.ui

import android.os.Bundle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import co.edu.umariana.inventario.data.ConteoEntity
import co.edu.umariana.inventario.ui.pantallas.ElegirScreen
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Elegir el conteo a partir del catálogo que mandó el PC. */
class ElegirActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private var conteos by mutableStateOf<List<ConteoEntity>?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pantalla {
            val lista = conteos ?: return@pantalla  // hasta que carga, solo el fondo
            ElegirScreen(
                lista, s.contar.conteo.value,
                alConfirmar = { conteo ->
                    s.contar.elegirConteo(conteo)
                    finish()
                },
                alVolver = { finish() },
                alSincronizar = { abrir(SincronizarActivity::class.java, Transicion.HOJA) },
            )
        }
    }

    override fun onResume() {
        super.onResume()  // al volver de sincronizar, el catálogo puede haber llegado
        lifecycleScope.launch {
            conteos = withContext(Dispatchers.IO) { s.contar.conteos() }
        }
    }
}
