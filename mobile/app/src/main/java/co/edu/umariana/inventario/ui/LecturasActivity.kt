package co.edu.umariana.inventario.ui

import android.os.Bundle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import co.edu.umariana.inventario.ui.pantallas.LecturaFila
import co.edu.umariana.inventario.ui.pantallas.LecturasScreen
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Lo contado en el conteo actual; tocar una fila la corrige (recontar). */
class LecturasActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private var filas by mutableStateOf<List<LecturaFila>?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pantalla {
            val lista = filas ?: return@pantalla
            LecturasScreen(
                s.contar.conteo.value, lista,
                alEditar = { fila ->
                    abrir(ContarActivity::class.java, Transicion.LATERAL) {
                        putExtra(ContarActivity.EXTRA_SKU, fila.sku)
                        putExtra(ContarActivity.EXTRA_CANTIDAD, fila.cantidad)
                        putExtra(ContarActivity.EXTRA_NOTA, fila.nota)
                    }
                },
                alContar = { abrir(ContarActivity::class.java) },
                alVolver = { finish() },
            )
        }
    }

    override fun onResume() {
        super.onResume()
        val conteo = s.contar.conteo.value
        lifecycleScope.launch {
            filas = if (conteo == null) emptyList() else withContext(Dispatchers.IO) {
                s.contar.lecturas().asReversed().map {
                    LecturaFila(it.sku, s.contar.producto(it.sku)?.nombre, it.cantidad, it.estado, it.nota)
                }
            }
        }
    }
}
