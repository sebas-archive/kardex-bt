package co.edu.umariana.inventario.ui

import android.content.Intent
import android.os.Bundle
import android.widget.ArrayAdapter
import android.widget.ListView
import androidx.lifecycle.lifecycleScope
import co.edu.umariana.inventario.data.LecturaEntity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Lo contado en la ubicación actual; tocar una fila la corrige (recontar). */
class LecturasActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private lateinit var lista: ListView
    private lateinit var encabezado: android.widget.TextView
    private var filas = emptyList<LecturaEntity>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        montar("Contado en esta ubicación")
        encabezado = texto("", 15f, negrita = true)
        lista = ListView(this).also { raiz.addView(it) }
        lista.setOnItemClickListener { _, _, posicion, _ ->
            val l = filas[posicion]
            startActivity(Intent(this, ContarActivity::class.java)
                .putExtra(ContarActivity.EXTRA_SKU, l.sku)
                .putExtra(ContarActivity.EXTRA_CANTIDAD, l.cantidad)
                .putExtra(ContarActivity.EXTRA_NOTA, l.nota))
        }
    }

    override fun onResume() {
        super.onResume()
        val ubicacion = s.contar.ubicacion.value
        if (ubicacion == null) {
            encabezado.text = "Elige primero el conteo y la ubicación"
            return
        }
        lifecycleScope.launch {
            val (lecturas, nombres) = withContext(Dispatchers.IO) {
                val ls = s.contar.lecturasDe(ubicacion)
                ls to ls.associate { it.sku to (s.contar.producto(it.sku)?.nombre ?: "SKU fuera del catálogo") }
            }
            filas = lecturas
            encabezado.text = "Ubicación $ubicacion · ${lecturas.size} productos · toca uno para corregirlo"
            lista.adapter = ArrayAdapter(this@LecturasActivity, android.R.layout.simple_list_item_1,
                lecturas.map { "${nombres[it.sku]} (${it.sku})  ×  ${it.cantidad}" })
            lista.layoutParams = lista.layoutParams.apply { height = dp(72) * maxOf(1, lecturas.size) }
        }
    }
}
