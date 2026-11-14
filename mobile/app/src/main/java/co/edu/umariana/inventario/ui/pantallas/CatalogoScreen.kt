package co.edu.umariana.inventario.ui.pantallas

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import co.edu.umariana.inventario.data.ProductoEntity
import co.edu.umariana.inventario.ui.Textos
import co.edu.umariana.inventario.ui.componentes.Entrada
import co.edu.umariana.inventario.ui.componentes.EstadoVacio
import co.edu.umariana.inventario.ui.componentes.Iconos
import co.edu.umariana.inventario.ui.componentes.Pantalla

/**
 * Catálogo: la lista simple de productos que mandó el PC para contar. No reemplaza a «Contar»: sirve para
 * consultar qué hay y abrir un producto con el SKU ya puesto.
 */
@Composable
fun CatalogoScreen(
    productos: List<ProductoEntity>,
    alContar: (sku: String) -> Unit,
    alSincronizar: () -> Unit,
    alVolver: () -> Unit,
) {
    var busqueda by remember { mutableStateOf("") }
    val filtrados = remember(productos, busqueda) {
        val q = busqueda.trim().lowercase()
        if (q.isEmpty()) productos else productos.filter {
            it.sku.lowercase().contains(q) || it.nombre.lowercase().contains(q) || it.categoria.lowercase().contains(q)
        }
    }
    Pantalla(
        titulo = Textos.t("Catálogo"),
        subtitulo = Textos.t("{n} productos", "n" to productos.size),
        alVolver = alVolver,
    ) {
        if (productos.isEmpty()) {
            EstadoVacio(Iconos.Caja, Textos.t("No hay productos en el catálogo"),
                Textos.t("Sincroniza con el PC para descargarlo.")) {
                TextButton(onClick = alSincronizar) { Text(Textos.t("Sincronizar")) }
            }
        } else {
            OutlinedTextField(
                value = busqueda, onValueChange = { busqueda = it },
                label = { Text(Textos.t("Buscar por SKU o nombre")) }, singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp),
            )
            if (filtrados.isEmpty()) {
                EstadoVacio(Iconos.Barras, Textos.t("Sin resultados"),
                    Textos.t("No hay productos que coincidan con «{q}».", "q" to busqueda.trim()))
            } else LazyColumn(
                Modifier.fillMaxSize(),
                contentPadding = PaddingValues(horizontal = 20.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                itemsIndexed(filtrados, key = { _, p -> p.sku }) { i, producto ->
                    Entrada(i.coerceAtMost(10)) { FilaProducto(producto) { alContar(producto.sku) } }
                }
            }
        }
    }
}

@Composable
private fun FilaProducto(producto: ProductoEntity, alPulsar: () -> Unit) {
    Surface(onClick = alPulsar, shape = MaterialTheme.shapes.medium, color = MaterialTheme.colorScheme.surface,
        shadowElevation = 1.dp, modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(horizontal = 14.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(40.dp).clip(CircleShape).background(MaterialTheme.colorScheme.surfaceVariant),
                contentAlignment = Alignment.Center,
            ) {
                Text(producto.nombre.take(1).uppercase(), style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary)
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(producto.nombre, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(producto.sku, style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("${producto.categoria} · ${producto.unidad}", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = Textos.t("Contar"),
                tint = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
