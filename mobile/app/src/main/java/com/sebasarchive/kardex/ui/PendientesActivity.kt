package com.sebasarchive.kardex.ui

import android.os.Bundle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import com.sebasarchive.kardex.ui.pantallas.PendienteFila
import com.sebasarchive.kardex.ui.pantallas.PendientesScreen
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Todas las lecturas guardadas con su estado: pendiente (no enviada), enviada (sin confirmar) o confirmada. */
class PendientesActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private var filas by mutableStateOf<List<PendienteFila>?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pantalla {
            val lista = filas ?: return@pantalla
            PendientesScreen(lista, alSincronizar = { abrir(SincronizarActivity::class.java, Transicion.HOJA) }, alVolver = { finish() })
        }
    }

    override fun onResume() {
        super.onResume()  // al volver de sincronizar los estados cambian
        lifecycleScope.launch {
            filas = withContext(Dispatchers.IO) { s.contar.todasLasLecturas() }.asReversed()
                .map { PendienteFila(it.seq, it.sku, it.cantidad, it.estado) }
        }
    }
}
