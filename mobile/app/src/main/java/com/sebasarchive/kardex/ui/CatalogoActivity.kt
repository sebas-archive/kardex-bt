package com.sebasarchive.kardex.ui

import android.os.Bundle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import com.sebasarchive.kardex.data.ProductoEntity
import com.sebasarchive.kardex.ui.pantallas.CatalogoScreen
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Catálogo: lista de productos con búsqueda. Tocar uno abre «Contar» con su SKU. */
class CatalogoActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private var productos by mutableStateOf<List<ProductoEntity>?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pantalla {
            val lista = productos ?: return@pantalla
            CatalogoScreen(
                lista,
                alContar = { sku ->
                    abrir(ContarActivity::class.java) {
                        putExtra(ContarActivity.EXTRA_SKU, sku)
                        putExtra(ContarActivity.EXTRA_NUEVO, true)  // viene del catálogo: contar, no corregir
                    }
                },
                alSincronizar = { abrir(SincronizarActivity::class.java, Transicion.HOJA) },
                alVolver = { finish() },
            )
        }
    }

    override fun onResume() {
        super.onResume()  // al volver de sincronizar puede haber catálogo nuevo
        lifecycleScope.launch {
            productos = withContext(Dispatchers.IO) { s.contar.productos() }
        }
    }
}
