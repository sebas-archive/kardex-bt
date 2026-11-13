package co.edu.umariana.inventario.ui.pantallas

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
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
import androidx.compose.ui.unit.dp
import co.edu.umariana.inventario.data.ConteoEntity
import co.edu.umariana.inventario.ui.componentes.Entrada
import co.edu.umariana.inventario.ui.componentes.EstadoVacio
import co.edu.umariana.inventario.ui.componentes.Iconos
import co.edu.umariana.inventario.ui.componentes.Pantalla

/** Elegir el conteo en el que se va a contar, de los que mandó el PC. */
@Composable
fun ElegirScreen(
    conteos: List<ConteoEntity>,
    conteoInicial: String?,
    alConfirmar: (conteo: String) -> Unit,
    alVolver: () -> Unit,
    alSincronizar: () -> Unit,
) {
    var conteo by remember(conteos, conteoInicial) {
        mutableStateOf(conteoInicial?.takeIf { id -> conteos.any { it.id == id } } ?: conteos.singleOrNull()?.id)
    }

    Pantalla(
        titulo = "Conteo", subtitulo = "En cuál vas a contar", alVolver = alVolver,
        barraInferior = if (conteos.isEmpty()) null else {
            {
                Button(onClick = { alConfirmar(conteo!!) }, enabled = conteo != null, modifier = Modifier.fillMaxWidth().height(54.dp)) {
                    Text(if (conteo != null) "Contar en $conteo" else "Elige un conteo")
                }
            }
        },
    ) {
        if (conteos.isEmpty()) {
            EstadoVacio(Iconos.Caja, "Todavía no hay catálogo",
                "Sincroniza una vez con el PC para descargar los conteos y los productos.") {
                Button(onClick = alSincronizar) { Text("Sincronizar con el PC") }
            }
        } else Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Conteos abiertos", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
            conteos.forEachIndexed { i, c ->
                Entrada(i) { TarjetaConteo(c, seleccionado = c.id == conteo) { conteo = c.id } }
            }
        }
    }
}

@Composable
private fun TarjetaConteo(conteo: ConteoEntity, seleccionado: Boolean, alElegir: () -> Unit) {
    val fondo by animateColorAsState(if (seleccionado) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface, label = "fondo")
    val borde by animateColorAsState(if (seleccionado) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant, label = "borde")
    Surface(onClick = alElegir, shape = MaterialTheme.shapes.medium, color = fondo,
        border = BorderStroke(if (seleccionado) 2.dp else 1.dp, borde), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(conteo.id, style = MaterialTheme.typography.titleMedium)
                Text(conteo.nombre, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            AnimatedVisibility(seleccionado,
                enter = scaleIn(spring(dampingRatio = Spring.DampingRatioMediumBouncy)) + fadeIn(), exit = scaleOut() + fadeOut()) {
                Icon(Icons.Default.CheckCircle, contentDescription = "Elegido", tint = MaterialTheme.colorScheme.primary)
            }
        }
    }
}
