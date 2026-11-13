package com.sebasarchive.kardex.ui.pantallas

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.animateIntAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.sebasarchive.kardex.ui.componentes.Entrada
import com.sebasarchive.kardex.ui.componentes.IconoEnCirculo
import com.sebasarchive.kardex.ui.componentes.Iconos
import com.sebasarchive.kardex.ui.componentes.escalaAlPulsar
import com.sebasarchive.kardex.ui.theme.Cifra
import com.sebasarchive.kardex.ui.theme.Marca

data class HomeUi(
    val operador: String = "",
    val rol: String = "Clasificador",
    val conteo: String? = null,
    val pendientes: Int = 0,
    val total: Int = 0,
    val hayCatalogo: Boolean = true,
)

/** Inicio: quién cuenta, dónde, cuánto falta por enviar y los cuatro caminos de la app. */
@Composable
fun HomeScreen(
    ui: HomeUi,
    alContar: () -> Unit,
    alElegir: () -> Unit,
    alLecturas: () -> Unit,
    alPendientes: () -> Unit,
    alSincronizar: () -> Unit,
    alPerfil: () -> Unit,
) {
    Surface(color = MaterialTheme.colorScheme.background, modifier = Modifier.fillMaxSize()) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Entrada(0) { Portada(ui, alElegir, alPerfil) }
            AnimatedVisibility(!ui.hayCatalogo, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
                AvisoSinCatalogo(alSincronizar)
            }
            Entrada(1) { TarjetaContar(alContar) }
            Entrada(2) {
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    TarjetaAccion(Icons.AutoMirrored.Filled.List, "Contado", "Lo que llevas en este conteo", alLecturas, Modifier.weight(1f))
                    TarjetaAccion(Icons.AutoMirrored.Filled.Send, "Pendientes",
                        if (ui.pendientes == 0) "Nada por enviar" else "${ui.pendientes} por enviar", alPendientes, Modifier.weight(1f))
                }
            }
            Entrada(3) { TarjetaSincronizar(ui.pendientes, alSincronizar) }
        }
    }
}

@Composable
private fun Portada(ui: HomeUi, alElegir: () -> Unit, alPerfil: () -> Unit) {
    // La cifra cuenta desde cero cada vez que cambia: se nota cuánto hay por enviar.
    val cifra by animateIntAsState(ui.pendientes, tween(900, easing = FastOutSlowInEasing), label = "pendientes")
    Box(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp))
            .background(Brush.linearGradient(listOf(Marca.Verde, Marca.VerdeProfundo)))
    ) {
        // Dos discos translúcidos: dan profundidad sin distraer.
        Box(Modifier.size(190.dp).align(Alignment.TopEnd).offset(x = 60.dp, y = (-70).dp).clip(CircleShape).background(Color.White.copy(alpha = 0.08f)))
        Box(Modifier.size(120.dp).align(Alignment.BottomEnd).offset(x = 30.dp, y = 40.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.06f)))
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(46.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.18f)), contentAlignment = Alignment.Center) {
                    Text(ui.operador.take(1).uppercase().ifEmpty { "?" }, color = Color.White, style = MaterialTheme.typography.titleLarge)
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("Hola,", color = Color.White.copy(alpha = 0.8f), style = MaterialTheme.typography.bodyMedium)
                    Text(ui.operador, color = Color.White, style = MaterialTheme.typography.titleLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Text(ui.rol, color = Color.White, style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.clip(RoundedCornerShape(50)).background(Color.White.copy(alpha = 0.18f)).padding(horizontal = 10.dp, vertical = 5.dp))
                IconButton(onClick = alPerfil) { Icon(Icons.Default.Person, contentDescription = "Mi cuenta", tint = Color.White) }
            }
            Row(verticalAlignment = Alignment.Bottom) {
                Text(cifra.toString(), style = MaterialTheme.typography.displayLarge.merge(Cifra), color = Color.White)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.padding(bottom = 10.dp)) {
                    Text(if (ui.pendientes == 1) "lectura por enviar" else "lecturas por enviar", color = Color.White, style = MaterialTheme.typography.titleMedium)
                    Text("${ui.total} guardadas en el teléfono", color = Color.White.copy(alpha = 0.75f), style = MaterialTheme.typography.bodySmall)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                DatoPortada("Conteo", ui.conteo ?: "Sin elegir", alElegir, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun DatoPortada(rotulo: String, valor: String, alPulsar: () -> Unit, modifier: Modifier = Modifier) {
    Column(
        modifier.clip(RoundedCornerShape(16.dp)).background(Color.White.copy(alpha = 0.14f)).clickable(onClick = alPulsar)
            .padding(horizontal = 14.dp, vertical = 10.dp)
    ) {
        Text(rotulo, color = Color.White.copy(alpha = 0.75f), style = MaterialTheme.typography.labelMedium)
        Text(valor, color = Color.White, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun AvisoSinCatalogo(alSincronizar: () -> Unit) {
    Surface(color = MaterialTheme.colorScheme.secondaryContainer, shape = MaterialTheme.shapes.medium) {
        Row(Modifier.padding(start = 16.dp, top = 12.dp, bottom = 12.dp, end = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.secondary)
            Spacer(Modifier.width(12.dp))
            Text("Todavía no hay catálogo. Sincroniza una vez con el PC para descargarlo.",
                Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSecondaryContainer)
            TextButton(onClick = alSincronizar) { Text("Sincronizar") }
        }
    }
}

@Composable
private fun TarjetaContar(alPulsar: () -> Unit) {
    val interaccion = remember { MutableInteractionSource() }
    Surface(
        onClick = alPulsar, interactionSource = interaccion, shape = MaterialTheme.shapes.large,
        color = MaterialTheme.colorScheme.primaryContainer, modifier = Modifier.fillMaxWidth().escalaAlPulsar(interaccion),
    ) {
        Row(Modifier.padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
            IconoEnCirculo(Iconos.Barras, MaterialTheme.colorScheme.primary, MaterialTheme.colorScheme.onPrimary, tam = 60)
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)) {
                Text("Contar", style = MaterialTheme.typography.headlineSmall, color = MaterialTheme.colorScheme.onPrimaryContainer)
                Text("Escanear barras o QR, o digitar", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onPrimaryContainer)
            }
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null, tint = MaterialTheme.colorScheme.onPrimaryContainer)
        }
    }
}

@Composable
private fun TarjetaAccion(icono: ImageVector, titulo: String, detalle: String, alPulsar: () -> Unit, modifier: Modifier = Modifier) {
    val interaccion = remember { MutableInteractionSource() }
    Surface(
        onClick = alPulsar, interactionSource = interaccion, shape = MaterialTheme.shapes.large,
        color = MaterialTheme.colorScheme.surface, shadowElevation = 2.dp, modifier = modifier.escalaAlPulsar(interaccion),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            IconoEnCirculo(icono, MaterialTheme.colorScheme.surfaceVariant, MaterialTheme.colorScheme.primary, tam = 44)
            Column {
                Text(titulo, style = MaterialTheme.typography.titleMedium)
                Text(detalle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

@Composable
private fun TarjetaSincronizar(pendientes: Int, alPulsar: () -> Unit) {
    val interaccion = remember { MutableInteractionSource() }
    Surface(
        onClick = alPulsar, interactionSource = interaccion, shape = MaterialTheme.shapes.large,
        color = MaterialTheme.colorScheme.tertiaryContainer, modifier = Modifier.fillMaxWidth().escalaAlPulsar(interaccion),
    ) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            IconoEnCirculo(Iconos.Bluetooth, MaterialTheme.colorScheme.tertiary, MaterialTheme.colorScheme.onTertiary, tam = 48)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text("Sincronizar con el PC", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onTertiaryContainer)
                Text(if (pendientes == 0) "Todo enviado" else "$pendientes lecturas esperando · sin claves ni códigos",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onTertiaryContainer)
            }
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null, tint = MaterialTheme.colorScheme.onTertiaryContainer)
        }
    }
}
