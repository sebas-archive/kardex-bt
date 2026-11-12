package co.edu.umariana.inventario.ui

import android.content.Intent
import android.os.Bundle
import android.widget.TextView
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Inicio: dónde está contando el operario y a dónde ir. Sin operador, lo pide primero. */
class HomeActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private lateinit var resumen: TextView
    private lateinit var alerta: TextView
    private var pidioOperador = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        montar("Inventario")
        resumen = texto("", 16f)
        alerta = texto("", 15f, negrita = true)
        boton("Contar") {
            if (s.contar.operador.value.isEmpty()) aviso("Escribe primero el nombre del operador")
            else if (s.contar.conteo.value == null || s.contar.ubicacion.value == null) aviso("Elige primero el conteo y la ubicación")
            else startActivity(Intent(this, ContarActivity::class.java))
        }
        boton("Elegir conteo y ubicación") { startActivity(Intent(this, ElegirActivity::class.java)) }
        boton("Contado en esta ubicación") { startActivity(Intent(this, LecturasActivity::class.java)) }
        boton("Pendientes de enviar") { startActivity(Intent(this, PendientesActivity::class.java)) }
        boton("Sincronizar con el PC") { startActivity(Intent(this, SincronizarActivity::class.java)) }
        boton("Cambiar operador") { startActivity(Intent(this, OperadorActivity::class.java)) }
    }

    override fun onResume() {
        super.onResume()
        if (s.contar.operador.value.isEmpty() && !pidioOperador) {  // primer uso: el operador es obligatorio antes de contar
            pidioOperador = true  // una sola vez: si vuelve atrás sin escribirlo no se le encierra en un ciclo
            startActivity(Intent(this, OperadorActivity::class.java))
            return
        }
        lifecycleScope.launch {
            val (pendientes, hayCatalogo) = withContext(Dispatchers.IO) { s.contar.contarPendientes() to s.contar.hayCatalogo() }
            resumen.text = "Operador: ${s.contar.operador.value.ifEmpty { "sin definir (toca «Cambiar operador»)" }}\n" +
                "Conteo: ${s.contar.conteo.value ?: "sin elegir"}\n" +
                "Ubicación: ${s.contar.ubicacion.value ?: "sin elegir"}\n" +
                "Lecturas por enviar: $pendientes"
            alerta.text = if (hayCatalogo) "" else
                "Todavía no hay catálogo: sincroniza una vez con el PC para descargar los conteos, ubicaciones y productos."
        }
    }
}
