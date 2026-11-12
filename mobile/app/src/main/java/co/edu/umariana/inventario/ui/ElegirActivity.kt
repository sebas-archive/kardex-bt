package co.edu.umariana.inventario.ui

import android.os.Bundle
import android.widget.ArrayAdapter
import android.widget.Spinner
import androidx.lifecycle.lifecycleScope
import co.edu.umariana.inventario.data.ConteoEntity
import co.edu.umariana.inventario.data.UbicacionEntity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Elegir conteo y ubicación a partir del catálogo que mandó el PC. */
class ElegirActivity : PantallaActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        montar("Conteo y ubicación")
        val s = Servicios.de(this)
        val aviso = texto("")
        texto("Conteo", 14f)
        val spConteo = Spinner(this).also { raiz.addView(it) }
        texto("Ubicación", 14f)
        val spUbic = Spinner(this).also { raiz.addView(it) }
        var conteos = emptyList<ConteoEntity>()
        var ubicaciones = emptyList<UbicacionEntity>()

        boton("Listo") {
            val c = conteos.getOrNull(spConteo.selectedItemPosition)
            val u = ubicaciones.getOrNull(spUbic.selectedItemPosition)
            if (c == null || u == null) aviso("No hay catálogo: sincroniza una vez con el PC")
            else {
                s.contar.elegirConteo(c.id)
                s.contar.elegirUbicacion(u.cod)
                finish()
            }
        }

        lifecycleScope.launch {
            val (cs, us) = withContext(Dispatchers.IO) { s.contar.conteos() to s.contar.ubicaciones() }
            conteos = cs
            ubicaciones = us
            if (cs.isEmpty()) aviso.text = "Todavía no hay catálogo. Sincroniza una vez con el PC para descargarlo."
            spConteo.adapter = ArrayAdapter(this@ElegirActivity, android.R.layout.simple_spinner_dropdown_item,
                cs.map { "${it.id} — ${it.nombre}" })
            spUbic.adapter = ArrayAdapter(this@ElegirActivity, android.R.layout.simple_spinner_dropdown_item,
                us.map { "${it.cod} — ${it.zona} · ${it.descripcion}" })
            cs.indexOfFirst { it.id == s.contar.conteo.value }.takeIf { it >= 0 }?.let { spConteo.setSelection(it) }
            us.indexOfFirst { it.cod == s.contar.ubicacion.value }.takeIf { it >= 0 }?.let { spUbic.setSelection(it) }
        }
    }
}
