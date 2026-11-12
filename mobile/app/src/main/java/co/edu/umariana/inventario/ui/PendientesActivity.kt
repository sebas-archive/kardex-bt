package co.edu.umariana.inventario.ui

import android.os.Bundle
import android.widget.ArrayAdapter
import android.widget.ListView
import androidx.lifecycle.lifecycleScope
import co.edu.umariana.inventario.data.Estado
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Todas las lecturas guardadas con su estado: PENDIENTE (no enviada), ENVIADO (sin confirmar) o CONFIRMADO. */
class PendientesActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        montar("Pendientes")
        val resumen = texto("", 15f, negrita = true)
        val lista = ListView(this).also { raiz.addView(it) }
        lifecycleScope.launch {
            val todas = withContext(Dispatchers.IO) { s.contar.todasLasLecturas() }.asReversed()
            val sinConfirmar = todas.count { it.estado != Estado.CONFIRMADO }
            resumen.text = if (todas.isEmpty()) "Todavía no hay lecturas" else
                "${todas.size} lecturas · $sinConfirmar por confirmar"
            lista.adapter = ArrayAdapter(this@PendientesActivity, android.R.layout.simple_list_item_1,
                todas.map { "#${it.seq} ${it.ubicacion} · ${it.sku} × ${it.cantidad}  —  ${it.estado}" })
            lista.layoutParams = lista.layoutParams.apply { height = dp(72) * maxOf(1, todas.size) }
        }
    }
}
