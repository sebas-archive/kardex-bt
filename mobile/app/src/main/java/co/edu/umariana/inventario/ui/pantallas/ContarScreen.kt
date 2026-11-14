package co.edu.umariana.inventario.ui.pantallas

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.TextButton
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import co.edu.umariana.inventario.data.ProductoEntity
import co.edu.umariana.inventario.ui.CountViewModel
import co.edu.umariana.inventario.ui.componentes.Iconos
import co.edu.umariana.inventario.ui.componentes.Pantalla
import co.edu.umariana.inventario.ui.componentes.escalaAlPulsar
import co.edu.umariana.inventario.ui.theme.Cifra
import co.edu.umariana.inventario.ui.theme.Marca

data class ContarUi(
    val conteo: String,
    val sku: String = "",
    val cantidad: String = "",
    val nota: String = "",
    val producto: ProductoEntity? = null,
    val skuDesconocido: Boolean = false,
    /** Cantidad ya contada de este SKU en este conteo (guardar la reemplaza), o null. */
    val previa: String? = null,
    val edicion: Boolean = false,
    val guardadas: Int = 0,
    val exito: Boolean = false,
    val error: String? = null,
    /** Fase 4: cuántas de las contadas están dañadas ("" = no se indica). */
    val danados: String = "",
    /** Fase 4: ruta del JPG ya comprimido que se adjuntará al guardar (null = sin foto nueva). */
    val foto: String? = null,
)

/** Contar: escanear o digitar el SKU, ver el producto, poner la cantidad y guardar. Sin red. */
@Composable
fun ContarScreen(
    ui: ContarUi,
    alCambiarSku: (String) -> Unit,
    alCambiarCantidad: (String) -> Unit,
    alCambiarNota: (String) -> Unit,
    alSumar: (Int) -> Unit,
    alEscanear: () -> Unit,
    alGuardar: () -> Unit,
    alVolver: () -> Unit,
    alCambiarDanados: (String) -> Unit = {},
    alCamara: () -> Unit = {},
    alGaleria: () -> Unit = {},
    alQuitarFoto: () -> Unit = {},
) {
    Box(Modifier.fillMaxSize()) {
        Pantalla(
            titulo = if (ui.edicion) "Corregir lectura" else "Contar",
            subtitulo = ui.conteo,
            alVolver = alVolver,
            barraInferior = {
                Button(onClick = alGuardar, modifier = Modifier.fillMaxWidth().height(56.dp)) {
                    Icon(Icons.Default.Check, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text(if (ui.edicion) "Guardar corrección" else "Guardar")
                }
                AnimatedVisibility(ui.guardadas > 0) {
                    Text("${ui.guardadas} guardadas en esta sesión", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center,
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
                }
            },
        ) {
            Column(
                Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                if (!ui.edicion) BotonEscanear(alEscanear)
                OutlinedTextField(
                    value = ui.sku, onValueChange = { if (it.length <= 40) alCambiarSku(it.replace("\n", "")) },
                    label = { Text("SKU, código de barras o QR") }, singleLine = true, enabled = !ui.edicion,
                    textStyle = MaterialTheme.typography.titleMedium.copy(fontFamily = FontFamily.Monospace),
                    modifier = Modifier.fillMaxWidth(),
                )
                // El producto aparece (o la advertencia) en cuanto el SKU se reconoce.
                AnimatedContent(
                    targetState = when {
                        ui.sku.isBlank() -> ""
                        ui.producto != null -> ui.producto.sku
                        ui.skuDesconocido -> "?"
                        else -> ""
                    },
                    transitionSpec = { (fadeIn(tween(220)) + slideInVertically(tween(260)) { -it / 3 }).togetherWith(fadeOut(tween(120))) },
                    label = "producto",
                ) { clave ->
                    when (clave) {
                        "" -> Spacer(Modifier.fillMaxWidth())
                        "?" -> TarjetaProducto(Icons.Default.Warning, "SKU fuera del catálogo",
                            "Se puede guardar igual; quedará pendiente de darlo de alta.",
                            MaterialTheme.colorScheme.secondaryContainer, MaterialTheme.colorScheme.secondary, MaterialTheme.colorScheme.onSecondaryContainer)
                        else -> TarjetaProducto(Icons.Default.CheckCircle, ui.producto?.nombre ?: clave,
                            ui.producto?.let { "${it.categoria} · ${it.unidad}" }.orEmpty(),
                            MaterialTheme.colorScheme.primaryContainer, MaterialTheme.colorScheme.primary, MaterialTheme.colorScheme.onPrimaryContainer)
                    }
                }
                AnimatedVisibility(ui.previa != null, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
                    Row(
                        Modifier.clip(RoundedCornerShape(50)).background(MaterialTheme.colorScheme.tertiaryContainer).padding(horizontal = 14.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Icons.Default.Refresh, contentDescription = null, tint = MaterialTheme.colorScheme.tertiary, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("Ya contado: ${ui.previa}. Guardar lo reemplaza.", style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onTertiaryContainer)
                    }
                }
                Cantidad(ui.cantidad, ui.producto?.unidad, alCambiarCantidad, alSumar)
                OutlinedTextField(
                    value = ui.danados, onValueChange = { if (it.length <= 13) alCambiarDanados(it.replace(',', '.')) },
                    label = { Text("Dañados o defectuosos (opcional)") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    supportingText = { Text("De las unidades contadas, cuántas están dañadas") },
                    modifier = Modifier.fillMaxWidth(),
                )
                Evidencia(ui.foto, alCamara, alGaleria, alQuitarFoto)
                OutlinedTextField(
                    value = ui.nota,
                    onValueChange = { if (it.codePointCount(0, it.length) <= CountViewModel.MAX_NOTA) alCambiarNota(it) },
                    label = { Text("Nota (opcional)") }, maxLines = 3,
                    supportingText = { Text("${ui.nota.codePointCount(0, ui.nota.length)}/${CountViewModel.MAX_NOTA}") },
                    modifier = Modifier.fillMaxWidth(),
                )
                AnimatedVisibility(ui.error != null, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
                    Surface(color = MaterialTheme.colorScheme.errorContainer, shape = MaterialTheme.shapes.medium) {
                        Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error)
                            Spacer(Modifier.width(10.dp))
                            Text(ui.error.orEmpty(), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onErrorContainer)
                        }
                    }
                }
            }
        }
        // Confirmación de guardado: un visto que salta en el centro y se va solo.
        AnimatedVisibility(
            ui.exito, modifier = Modifier.align(Alignment.Center),
            enter = scaleIn(spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessMediumLow)) + fadeIn(),
            exit = fadeOut(tween(250)),
        ) {
            val onda = remember { Animatable(0f) }
            LaunchedEffect(Unit) { onda.animateTo(1f, tween(750, easing = FastOutSlowInEasing)) }
            Box(contentAlignment = Alignment.Center) {
                // Una onda verde se abre alrededor del visto y se desvanece.
                Box(Modifier.size(136.dp).graphicsLayer {
                    scaleX = 1f + 2.4f * onda.value; scaleY = 1f + 2.4f * onda.value; alpha = (1f - onda.value) * 0.45f
                }.clip(CircleShape).background(Marca.Confirmado))
                Box(Modifier.size(136.dp).shadow(16.dp, CircleShape).clip(CircleShape).background(Marca.Confirmado), contentAlignment = Alignment.Center) {
                    Icon(Icons.Default.Check, contentDescription = "Guardado", tint = Color.White, modifier = Modifier.size(76.dp))
                }
            }
        }
    }
}

/** Foto de evidencia: tomarla o elegirla, y su miniatura de confirmación. */
@Composable
private fun Evidencia(foto: String?, alCamara: () -> Unit, alGaleria: () -> Unit, alQuitar: () -> Unit) {
    val miniatura = remember(foto) {
        foto?.let { BitmapFactory.decodeFile(it, BitmapFactory.Options().apply { inSampleSize = 4 })?.asImageBitmap() }
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Foto de evidencia (opcional)", style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
            FilledTonalButton(onClick = alCamara) { Text("📷  Cámara") }
            OutlinedButton(onClick = alGaleria) { Text("Galería") }
        }
        if (miniatura != null) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Image(miniatura, contentDescription = "Foto adjunta", contentScale = ContentScale.Crop,
                    modifier = Modifier.size(84.dp).clip(RoundedCornerShape(12.dp)))
                Column {
                    Text("Se adjuntará al guardar", style = MaterialTheme.typography.bodyMedium)
                    TextButton(onClick = alQuitar) { Text("Quitar") }
                }
            }
        }
    }
}

@Composable
private fun BotonEscanear(alPulsar: () -> Unit) {
    val interaccion = remember { MutableInteractionSource() }
    val laser by rememberInfiniteTransition(label = "laser").animateFloat(
        0.2f, 0.8f, infiniteRepeatable(tween(1100, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "y")
    Surface(onClick = alPulsar, interactionSource = interaccion, shape = MaterialTheme.shapes.large,
        color = MaterialTheme.colorScheme.primary, modifier = Modifier.fillMaxWidth().escalaAlPulsar(interaccion)) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(56.dp).clip(RoundedCornerShape(16.dp)).background(Color.White.copy(alpha = 0.16f))
                    .drawWithContent {
                        drawContent()
                        val y = size.height * laser  // la línea del lector sube y baja
                        drawLine(Color(0xFFFF8A80), Offset(8.dp.toPx(), y), Offset(size.width - 8.dp.toPx(), y),
                            strokeWidth = 2.dp.toPx(), cap = StrokeCap.Round)
                    },
                contentAlignment = Alignment.Center,
            ) { Icon(Iconos.Qr, contentDescription = null, tint = Color.White, modifier = Modifier.size(30.dp)) }
            Spacer(Modifier.width(14.dp))
            Column {
                Text("Escanear código de barras o QR", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onPrimary)
                Text("Con la cámara · funciona sin red", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.85f))
            }
        }
    }
}

@Composable
private fun TarjetaProducto(icono: ImageVector, titulo: String, detalle: String, fondo: Color, tinte: Color, texto: Color) {
    Surface(color = fondo, shape = MaterialTheme.shapes.medium, modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icono, contentDescription = null, tint = tinte, modifier = Modifier.size(28.dp))
            Spacer(Modifier.width(12.dp))
            Column {
                Text(titulo, style = MaterialTheme.typography.titleMedium, color = texto)
                if (detalle.isNotEmpty()) Text(detalle, style = MaterialTheme.typography.bodySmall, color = texto)
            }
        }
    }
}

@Composable
private fun Cantidad(valor: String, unidad: String?, alCambiar: (String) -> Unit, alSumar: (Int) -> Unit) {
    val escala = remember { Animatable(1f) }
    LaunchedEffect(valor) {  // la cifra «salta» cada vez que cambia
        if (valor.isNotEmpty()) {
            escala.snapTo(1.14f)
            escala.animateTo(1f, spring(dampingRatio = 0.45f, stiffness = Spring.StiffnessMedium))
        }
    }
    val haptica = LocalHapticFeedback.current
    val estilo = MaterialTheme.typography.displayMedium.merge(Cifra).copy(textAlign = TextAlign.Center)
    val colores = IconButtonDefaults.filledTonalIconButtonColors(
        containerColor = MaterialTheme.colorScheme.primaryContainer, contentColor = MaterialTheme.colorScheme.onPrimaryContainer)
    Surface(color = MaterialTheme.colorScheme.surface, shape = MaterialTheme.shapes.large, shadowElevation = 2.dp, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 14.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(if (unidad.isNullOrBlank()) "Cantidad" else "Cantidad ($unidad)", style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(verticalAlignment = Alignment.CenterVertically) {
                FilledTonalIconButton(
                    onClick = { haptica.performHapticFeedback(HapticFeedbackType.TextHandleMove); alSumar(-1) },
                    modifier = Modifier.size(60.dp), colors = colores,
                ) { Icon(Iconos.Menos, contentDescription = "Restar uno", modifier = Modifier.size(28.dp)) }
                BasicTextField(
                    value = valor,
                    onValueChange = { nuevo -> if (nuevo.length <= 13 && nuevo.all { it.isDigit() || it == '.' }) alCambiar(nuevo) },
                    textStyle = estilo.copy(color = MaterialTheme.colorScheme.onSurface),
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                    modifier = Modifier.weight(1f).padding(horizontal = 8.dp).graphicsLayer { scaleX = escala.value; scaleY = escala.value },
                    decorationBox = { campo ->
                        Box(contentAlignment = Alignment.Center) {
                            if (valor.isEmpty()) Text("0", style = estilo, color = MaterialTheme.colorScheme.outlineVariant, modifier = Modifier.fillMaxWidth())
                            campo()
                        }
                    },
                )
                FilledTonalIconButton(
                    onClick = { haptica.performHapticFeedback(HapticFeedbackType.TextHandleMove); alSumar(1) },
                    modifier = Modifier.size(60.dp), colors = colores,
                ) { Icon(Icons.Default.Add, contentDescription = "Sumar uno", modifier = Modifier.size(28.dp)) }
            }
        }
    }
}
