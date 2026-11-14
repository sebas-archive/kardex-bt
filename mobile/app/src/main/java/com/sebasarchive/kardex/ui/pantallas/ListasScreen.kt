package com.sebasarchive.kardex.ui.pantallas

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.sebasarchive.kardex.data.Estado
import com.sebasarchive.kardex.ui.componentes.Entrada
import com.sebasarchive.kardex.ui.componentes.EstadoVacio
import com.sebasarchive.kardex.ui.componentes.Iconos
import com.sebasarchive.kardex.ui.componentes.NumeroAnimado
import com.sebasarchive.kardex.ui.componentes.Pantalla
import com.sebasarchive.kardex.ui.componentes.PildoraEstado
import com.sebasarchive.kardex.ui.componentes.colorDeEstado
import com.sebasarchive.kardex.ui.componentes.textoDeEstado
import com.sebasarchive.kardex.ui.theme.Cifra

data class LecturaFila(val sku: String, val nombre: String?, val cantidad: String, val estado: String, val nota: String,
                       val foto: Boolean = false, val danados: String = "")

/** Lo contado en el conteo actual; tocar una fila la corrige (recontar). */
@Composable
fun LecturasScreen(conteo: String?, filas: List<LecturaFila>, alEditar: (LecturaFila) -> Unit, alContar: () -> Unit, alVolver: () -> Unit) {
    Pantalla(
        titulo = "Contado",
        subtitulo = if (conteo == null) "Sin conteo elegido" else "$conteo · ${filas.size} productos",
        alVolver = alVolver,
        barraInferior = if (conteo == null || filas.isEmpty()) null else {
            { Button(onClick = alContar, modifier = Modifier.fillMaxWidth().height(54.dp)) { Text("Contar otro producto") } }
        },
    ) {
        if (filas.isEmpty()) {
            EstadoVacio(Iconos.Barras, if (conteo == null) "Elige primero el conteo" else "Aún no has contado nada",
                "Cada producto que guardes aparece en esta lista. Tocar uno permite corregir su cantidad.") {
                if (conteo != null) Button(onClick = alContar) { Text("Contar") }
            }
        } else LazyColumn(
            Modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 20.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            itemsIndexed(filas, key = { _, f -> f.sku }) { i, fila ->
                Entrada(i.coerceAtMost(8), Modifier.animateItemPlacement()) { TarjetaLectura(fila) { alEditar(fila) } }
            }
        }
    }
}

@Composable
private fun TarjetaLectura(fila: LecturaFila, alPulsar: () -> Unit) {
    Surface(onClick = alPulsar, shape = MaterialTheme.shapes.medium, color = MaterialTheme.colorScheme.surface, shadowElevation = 1.dp,
        modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(fila.nombre ?: "SKU fuera del catálogo", style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    color = if (fila.nombre == null) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.onSurface)
                Text(fila.sku, style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    PildoraEstado(fila.estado)
                    if (fila.foto) Text("  📷", style = MaterialTheme.typography.bodySmall)
                    if (fila.danados.isNotBlank()) {
                        Text("  ${fila.danados} dañados", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                    }
                    if (fila.nota.isNotBlank()) {
                        Spacer(Modifier.width(8.dp))
                        Text(fila.nota, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
            Spacer(Modifier.width(10.dp))
            Box(Modifier.clip(RoundedCornerShape(14.dp)).background(MaterialTheme.colorScheme.primaryContainer).padding(horizontal = 14.dp, vertical = 8.dp)) {
                Text(fila.cantidad, style = MaterialTheme.typography.titleLarge.merge(Cifra), color = MaterialTheme.colorScheme.onPrimaryContainer)
            }
            Spacer(Modifier.width(8.dp))
            Icon(Icons.Default.Edit, contentDescription = "Corregir", tint = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.size(20.dp))
        }
    }
}

data class PendienteFila(val seq: Long, val sku: String, val cantidad: String, val estado: String)

/** Todas las lecturas guardadas con su estado; los contadores de arriba filtran la lista. */
@Composable
fun PendientesScreen(filas: List<PendienteFila>, alSincronizar: () -> Unit, alVolver: () -> Unit) {
    var filtro by remember { mutableStateOf<String?>(null) }
    val porEnviar = filas.count { it.estado != Estado.CONFIRMADO }
    Pantalla(
        titulo = "Pendientes", subtitulo = "${filas.size} lecturas en el teléfono", alVolver = alVolver,
        barraInferior = if (porEnviar == 0) null else {
            {
                Button(onClick = alSincronizar, modifier = Modifier.fillMaxWidth().height(54.dp)) {
                    Icon(Iconos.Bluetooth, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("Sincronizar $porEnviar lecturas")
                }
            }
        },
    ) {
        if (filas.isEmpty()) {
            EstadoVacio(Icons.AutoMirrored.Filled.Send, "Todavía no hay lecturas", "Lo que cuentes se guarda en el teléfono y aparece aquí hasta que el PC lo confirme.")
        } else {
            Row(Modifier.padding(horizontal = 20.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                for (estado in listOf(Estado.PENDIENTE, Estado.ENVIADO, Estado.CONFIRMADO)) {
                    Contador(estado, filas.count { it.estado == estado }, filtro == estado, Modifier.weight(1f)) {
                        filtro = if (filtro == estado) null else estado
                    }
                }
            }
            val visibles = filas.filter { filtro == null || it.estado == filtro }
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 20.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(visibles, key = { it.seq }) { fila ->
                    Surface(shape = MaterialTheme.shapes.medium, color = MaterialTheme.colorScheme.surface, shadowElevation = 1.dp,
                        modifier = Modifier.fillMaxWidth().animateItemPlacement()) {
                        Row(Modifier.padding(horizontal = 14.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(40.dp).clip(CircleShape).background(MaterialTheme.colorScheme.surfaceVariant), contentAlignment = Alignment.Center) {
                                Text("${fila.seq}", style = MaterialTheme.typography.labelLarge.merge(Cifra), color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Text(fila.sku, style = MaterialTheme.typography.titleMedium.copy(fontFamily = FontFamily.Monospace), maxLines = 1,
                                    overflow = TextOverflow.Ellipsis)
                                Text("× ${fila.cantidad}", style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            PildoraEstado(fila.estado)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Contador(estado: String, cantidad: Int, seleccionado: Boolean, modifier: Modifier = Modifier, alPulsar: () -> Unit) {
    val color = colorDeEstado(estado)
    val fondo by animateColorAsState(if (seleccionado) color.copy(alpha = 0.16f) else MaterialTheme.colorScheme.surface, label = "fondo")
    Surface(onClick = alPulsar, shape = MaterialTheme.shapes.medium, color = fondo, shadowElevation = if (seleccionado) 0.dp else 1.dp,
        border = if (seleccionado) BorderStroke(2.dp, color) else null, modifier = modifier) {
        Column(Modifier.padding(12.dp)) {
            Box(Modifier.size(10.dp).clip(CircleShape).background(color))
            NumeroAnimado(cantidad, MaterialTheme.typography.headlineSmall.merge(Cifra), MaterialTheme.colorScheme.onSurface)
            Text(textoDeEstado(estado) + "s", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
