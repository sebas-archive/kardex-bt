package co.edu.umariana.inventario.ui.componentes

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.SizeTransform
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.MutableTransitionState
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.InteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import co.edu.umariana.inventario.data.Estado
import co.edu.umariana.inventario.ui.theme.Marca

/** Iconos propios (trazos de 24 × 24): los que no vienen en el juego básico de Material. */
object Iconos {
    private fun icono(nombre: String, trazo: String): ImageVector =
        ImageVector.Builder(name = nombre, defaultWidth = 24.dp, defaultHeight = 24.dp, viewportWidth = 24f, viewportHeight = 24f)
            .addPath(pathData = addPathNodes(trazo), fill = SolidColor(Color.Black))
            .build()

    val Bluetooth by lazy {
        icono("Bluetooth", "M17.71,7.71L12,2h-1v7.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L11,14.41V22h1l5.71,-5.71l-4.3,-4.29l4.3,-4.29zM13,5.83l1.88,1.88L13,9.59V5.83zM14.88,16.29L13,18.17v-3.76l1.88,1.88z")
    }
    val Barras by lazy {
        icono("Barras", "M2,5h2v14H2zM6,5h1v14H6zM9,5h3v14H9zM14,5h1v14h-1zM17,5h2v14h-2zM21,5h1v14h-1z")
    }
    val Menos by lazy { icono("Menos", "M19,13H5v-2h14v2z") }
    val Caja by lazy {
        icono("Caja", "M20,2H4C3,2 2,2.9 2,4v3.01c0,0.72 0.43,1.34 1,1.69V20c0,1.1 1.1,2 2,2h14c0.9,0 2,-0.9 2,-2V8.7c0.57,-0.35 1,-0.97 1,-1.69V4C22,2.9 21,2 20,2zM15,14H9v-2h6V14zM20,7H4V4h16V7z")
    }
    val Qr by lazy {
        icono("Qr", "M3,3h8v8H3zM5,5v4h4V5zM13,3h8v8h-8zM15,5v4h4V5zM3,13h8v8H3zM5,15v4h4v-4zM13,13h3v3h-3zM18,13h3v3h-3zM13,18h3v3h-3zM18,18h3v3h-3zM16,16h2v2h-2z")
    }
    val Ojo by lazy {
        icono("Ojo", "M12,4.5C7,4.5 2.73,7.61 1,12c1.73,4.39 6,7.5 11,7.5s9.27,-3.11 11,-7.5C21.27,7.61 17,4.5 12,4.5zM12,17c-2.76,0 -5,-2.24 -5,-5s2.24,-5 5,-5s5,2.24 5,5S14.76,17 12,17zM12,9c-1.66,0 -3,1.34 -3,3s1.34,3 3,3s3,-1.34 3,-3S13.66,9 12,9z")
    }
    val Sincronizar by lazy {
        icono("Sincronizar", "M12,4V1L8,5l4,4V6c3.31,0 6,2.69 6,6c0,1.01 -0.25,1.97 -0.7,2.8l1.46,1.46C19.54,15.03 20,13.57 20,12C20,7.58 16.42,4 12,4zM12,18c-3.31,0 -6,-2.69 -6,-6c0,-1.01 0.25,-1.97 0.7,-2.8L5.24,7.74C4.46,8.97 4,10.43 4,12c0,4.42 3.58,8 8,8v3l4,-4l-4,-4V18z")
    }
}

/** Estructura común: barra con título, contenido y, si hace falta, una barra inferior fija. */
@Composable
fun Pantalla(
    titulo: String,
    subtitulo: String? = null,
    alVolver: (() -> Unit)? = null,
    acciones: @Composable RowScope.() -> Unit = {},
    barraInferior: (@Composable ColumnScope.() -> Unit)? = null,
    contenido: @Composable ColumnScope.() -> Unit,
) {
    val llegada = remember { MutableTransitionState(false).apply { targetState = true } }
    Surface(color = MaterialTheme.colorScheme.background, modifier = Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            // El título llega desde la izquierda y la barra inferior sube: cada pantalla «se arma» al abrirse.
            AnimatedVisibility(llegada, enter = fadeIn(tween(300)) + slideInHorizontally(tween(420, easing = FastOutSlowInEasing)) { -it / 4 }) {
            Row(
                Modifier.fillMaxWidth().padding(start = if (alVolver != null) 4.dp else 20.dp, end = 12.dp, top = 12.dp, bottom = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (alVolver != null) {
                    IconButton(onClick = alVolver) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = co.edu.umariana.inventario.ui.Textos.t("Volver")) }
                }
                Column(Modifier.weight(1f)) {
                    Text(titulo, style = MaterialTheme.typography.titleLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (subtitulo != null) {
                        Text(subtitulo, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                acciones()
                BotonApariencia()
            }
            }
            Column(Modifier.weight(1f).fillMaxWidth(), content = contenido)
            if (barraInferior != null) {
                AnimatedVisibility(llegada, enter = slideInVertically(tween(460, delayMillis = 120, easing = FastOutSlowInEasing)) { it } + fadeIn(tween(300, delayMillis = 120))) {
                    Surface(shadowElevation = 12.dp, color = MaterialTheme.colorScheme.surface) {
                        Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 14.dp), content = barraInferior)
                    }
                }
            }
        }
    }
}

/** Entrada escalonada: cada bloque sube, crece y aparece, [indice] × 55 ms después del anterior. */
@Composable
fun Entrada(indice: Int, modifier: Modifier = Modifier, contenido: @Composable () -> Unit) {
    val estado = remember { MutableTransitionState(false).apply { targetState = true } }
    val retraso = (indice * 55).coerceAtMost(440)
    AnimatedVisibility(
        visibleState = estado,
        modifier = modifier,
        enter = fadeIn(tween(320, delayMillis = retraso)) +
            slideInVertically(tween(420, delayMillis = retraso, easing = FastOutSlowInEasing)) { it / 2 } +
            scaleIn(tween(420, delayMillis = retraso, easing = FastOutSlowInEasing), initialScale = 0.9f),
    ) { contenido() }
}

/** El elemento se encoge un poco mientras se mantiene pulsado y rebota al soltar. */
fun Modifier.escalaAlPulsar(interaccion: InteractionSource): Modifier = composed {
    val pulsado by interaccion.collectIsPressedAsState()
    val escala by animateFloatAsState(
        if (pulsado) 0.96f else 1f,
        spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessMedium), label = "pulsar")
    graphicsLayer { scaleX = escala; scaleY = escala }
}

/** Un entero que cambia rodando hacia arriba o hacia abajo según suba o baje. */
@Composable
fun NumeroAnimado(valor: Int, estilo: TextStyle, color: Color, modifier: Modifier = Modifier) {
    AnimatedContent(
        targetState = valor,
        modifier = modifier,
        transitionSpec = {
            val sube = targetState > initialState
            (slideInVertically(tween(260)) { if (sube) it else -it } + fadeIn(tween(260)))
                .togetherWith(slideOutVertically(tween(260)) { if (sube) -it else it } + fadeOut(tween(200)))
                .using(SizeTransform(clip = false))
        },
        label = "numero",
    ) { n -> Text(n.toString(), style = estilo, color = color) }
}

fun colorDeEstado(estado: String): Color = when (estado) {
    Estado.CONFIRMADO -> Marca.Confirmado
    Estado.ENVIADO -> Marca.Enviado
    else -> Marca.Pendiente
}

fun textoDeEstado(estado: String): String = co.edu.umariana.inventario.ui.Textos.estadoLectura(estado)

/** Píldora con punto de color: el estado de una lectura. */
@Composable
fun PildoraEstado(estado: String, modifier: Modifier = Modifier) {
    val color = colorDeEstado(estado)
    Row(
        modifier.clip(RoundedCornerShape(50)).background(color.copy(alpha = 0.14f)).padding(horizontal = 10.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(color))
        Spacer(Modifier.width(6.dp))
        Text(textoDeEstado(estado), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurface)
    }
}

/** Círculo con un icono dentro. */
@Composable
fun IconoEnCirculo(icono: ImageVector, fondo: Color, tinte: Color, tam: Int = 48, modifier: Modifier = Modifier) {
    Box(modifier.size(tam.dp).clip(CircleShape).background(fondo), contentAlignment = Alignment.Center) {
        Icon(icono, contentDescription = null, tint = tinte, modifier = Modifier.size((tam * 0.5f).dp))
    }
}

/** Lo que se muestra cuando una lista no tiene nada. */
@Composable
fun EstadoVacio(icono: ImageVector, titulo: String, detalle: String, modifier: Modifier = Modifier, accion: (@Composable () -> Unit)? = null) {
    Column(
        modifier.fillMaxWidth().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        IconoEnCirculo(icono, MaterialTheme.colorScheme.surfaceVariant, MaterialTheme.colorScheme.onSurfaceVariant, tam = 88)
        Text(titulo, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        Text(detalle, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
        accion?.invoke()
    }
}
