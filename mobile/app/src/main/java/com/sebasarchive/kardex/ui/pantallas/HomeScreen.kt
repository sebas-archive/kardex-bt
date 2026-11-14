package com.sebasarchive.kardex.ui.pantallas

import android.graphics.BitmapFactory
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.animateIntAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.Image
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
import androidx.compose.material.icons.filled.Notifications
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
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.sebasarchive.kardex.ui.Textos
import com.sebasarchive.kardex.ui.componentes.Entrada
import com.sebasarchive.kardex.ui.componentes.IconoEnCirculo
import com.sebasarchive.kardex.ui.componentes.Iconos
import com.sebasarchive.kardex.ui.componentes.escalaAlPulsar
import com.sebasarchive.kardex.ui.theme.Cifra
import com.sebasarchive.kardex.ui.theme.Marca

data class HomeUi(
    val operador: String = "",
    val rol: String = "Operador de Inventario",
    val pendientes: Int = 0,
    val total: Int = 0,
    val hayCatalogo: Boolean = true,
    val fotosPendientes: Int = 0,
    /** Ruta del JPG de la foto de perfil; null = inicial. */
    val foto: String? = null,
    val noLeidas: Int = 0,
)

/** Inicio: quién cuenta, cuánto falta por enviar y los caminos de la app. Sin tarea: el conteo es continuo. */
@Composable
fun HomeScreen(
    ui: HomeUi,
    alContar: () -> Unit,
    alCatalogo: () -> Unit,
    alLecturas: () -> Unit,
    alPendientes: () -> Unit,
    alSincronizar: () -> Unit,
    alNotificaciones: () -> Unit,
    alPerfil: () -> Unit,
) {
    Surface(color = MaterialTheme.colorScheme.background, modifier = Modifier.fillMaxSize()) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Entrada(0) { Portada(ui, alNotificaciones, alPerfil) }
            AnimatedVisibility(!ui.hayCatalogo, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
                AvisoSinCatalogo(alSincronizar)
            }
            Entrada(1) { TarjetaContar(alContar) }
            Entrada(2) {
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    TarjetaAccion(Iconos.Caja, Textos.t("Catálogo"), Textos.t("Productos del catálogo"), alCatalogo, Modifier.weight(1f))
                    TarjetaAccion(Icons.AutoMirrored.Filled.List, Textos.t("Contado"),
                        Textos.t("Lo que has contado"), alLecturas, Modifier.weight(1f))
                }
            }
            Entrada(3) {
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    TarjetaAccion(Icons.AutoMirrored.Filled.Send, Textos.t("Pendientes"),
                        if (ui.pendientes == 0) Textos.t("Nada por enviar")
                        else Textos.t("{n} por enviar", "n" to ui.pendientes), alPendientes, Modifier.weight(1f))
                }
            }
            Entrada(4) { TarjetaSincronizar(ui.pendientes, alSincronizar) }
        }
    }
}

@Composable
private fun Portada(ui: HomeUi, alNotificaciones: () -> Unit, alPerfil: () -> Unit) {
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
                Avatar(ui.foto, ui.operador, 46)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(Textos.t("Hola,"), color = Color.White.copy(alpha = 0.8f), style = MaterialTheme.typography.bodyMedium)
                    Text(ui.operador, color = Color.White, style = MaterialTheme.typography.titleLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(Textos.rol(ui.rol), color = Color.White.copy(alpha = 0.75f), style = MaterialTheme.typography.bodySmall,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Campana(ui.noLeidas, alNotificaciones)
                IconButton(onClick = alPerfil) { Icon(Icons.Default.Person, contentDescription = Textos.t("Mi cuenta"), tint = Color.White) }
            }
            Row(verticalAlignment = Alignment.Bottom) {
                Text(cifra.toString(), style = MaterialTheme.typography.displayLarge.merge(Cifra), color = Color.White)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.padding(bottom = 10.dp)) {
                    Text(Textos.n(ui.pendientes, "lectura por enviar", "lecturas por enviar"), color = Color.White, style = MaterialTheme.typography.titleMedium)
                    Text(Textos.t("{n} guardadas en el teléfono", "n" to ui.total), color = Color.White.copy(alpha = 0.75f), style = MaterialTheme.typography.bodySmall)
                    if (ui.fotosPendientes > 0) {
                        Text(
                            if (ui.fotosPendientes == 1) Textos.t("📷 1 foto por enviar")
                            else Textos.t("📷 {n} fotos por enviar", "n" to ui.fotosPendientes),
                            color = Color.White.copy(alpha = 0.75f), style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }
        }
    }
}

/** Avatar circular: la foto recortada si existe; si no, la inicial del nombre. */
@Composable
fun Avatar(foto: String?, nombre: String, tam: Int, modifier: Modifier = Modifier) {
    val imagen = remember(foto) {
        foto?.let { BitmapFactory.decodeFile(it)?.asImageBitmap() }
    }
    Box(
        modifier.size(tam.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.18f)),
        contentAlignment = Alignment.Center,
    ) {
        if (imagen != null) {
            Image(imagen, contentDescription = Textos.t("Foto de perfil"), contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize().clip(CircleShape))
        } else {
            Text(nombre.take(1).uppercase().ifEmpty { "?" }, color = Color.White,
                style = MaterialTheme.typography.titleLarge)
        }
    }
}

@Composable
private fun Campana(noLeidas: Int, alPulsar: () -> Unit) {
    Box {
        IconButton(onClick = alPulsar) {
            Icon(Icons.Default.Notifications, contentDescription = Textos.t("Abrir notificaciones"), tint = Color.White)
        }
        if (noLeidas > 0) {
            Box(
                Modifier.size(18.dp).align(Alignment.TopEnd).offset(x = (-8).dp, y = 6.dp).clip(CircleShape)
                    .background(MaterialTheme.colorScheme.error), contentAlignment = Alignment.Center,
            ) {
                Text(if (noLeidas > 9) "9+" else noLeidas.toString(), color = Color.White,
                    style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

@Composable
private fun AvisoSinCatalogo(alSincronizar: () -> Unit) {
    Surface(color = MaterialTheme.colorScheme.secondaryContainer, shape = MaterialTheme.shapes.medium) {
        Row(Modifier.padding(start = 16.dp, top = 12.dp, bottom = 12.dp, end = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.secondary)
            Spacer(Modifier.width(12.dp))
            Text(Textos.t("Todavía no hay catálogo. Sincroniza una vez con el PC para descargarlo."),
                Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSecondaryContainer)
            TextButton(onClick = alSincronizar) { Text(Textos.t("Sincronizar")) }
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
                Text(Textos.t("Contar"), style = MaterialTheme.typography.headlineSmall, color = MaterialTheme.colorScheme.onPrimaryContainer)
                Text(Textos.t("Escanear barras o QR, o digitar"), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onPrimaryContainer)
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
                Text(Textos.t("Sincronizar con el PC"), style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onTertiaryContainer)
                Text(
                    if (pendientes == 0) Textos.t("Todo enviado")
                    else Textos.t("{n} lecturas esperando · sin claves ni códigos", "n" to pendientes),
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onTertiaryContainer,
                )
            }
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null, tint = MaterialTheme.colorScheme.onTertiaryContainer)
        }
    }
}
