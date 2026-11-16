package com.sebasarchive.kardex.ui.pantallas

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
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
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.sebasarchive.kardex.sync.PcConnector
import com.sebasarchive.kardex.ui.Textos
import com.sebasarchive.kardex.ui.SyncEstado
import com.sebasarchive.kardex.ui.componentes.Entrada
import com.sebasarchive.kardex.ui.componentes.IconoEnCirculo
import com.sebasarchive.kardex.ui.componentes.Iconos
import com.sebasarchive.kardex.ui.componentes.Pantalla
import com.sebasarchive.kardex.ui.theme.Cifra
import com.sebasarchive.kardex.ui.theme.Marca
import kotlin.math.roundToInt

data class SincronizarUi(
    val pcNombre: String? = null,
    val pcDireccion: String? = null,
    val estado: SyncEstado? = null,
    /** Lecturas confirmadas y por enviar en esta sincronización (para el anillo de progreso). */
    val enviadas: Long = 0,
    val porEnviar: Long = 0,
    val buscando: Boolean = false,
    /** PCs encontrados al buscar: dirección Bluetooth y nombre. */
    val encontrados: List<Pair<String, String>> = emptyList(),
    /** Aviso que no viene de la sincronización: permisos, Bluetooth apagado, búsqueda sin resultado. */
    val mensaje: String? = null,
    val pendientes: Int = 0,
    /** Cualquier operador puede cambiar el PC; no hay roles de supervisión en el teléfono. */
    val puedeCambiarPc: Boolean = true,
    /** La app se abrió sin sesión: solo se comprueba la conexión con el PC y después sigue el acceso. */
    val soloConectar: Boolean = false,
)

private enum class Fase { REPOSO, RADAR, PROGRESO, LISTO, OCUPADO, ERROR }

private fun SincronizarUi.fase(): Fase = when (estado) {
    null -> if (buscando) Fase.RADAR else Fase.REPOSO
    is SyncEstado.Conectando, is SyncEstado.Reintentando -> Fase.RADAR
    is SyncEstado.Sincronizando -> Fase.PROGRESO
    is SyncEstado.Listo -> Fase.LISTO
    SyncEstado.Ocupado -> Fase.OCUPADO
    is SyncEstado.Rechazado, is SyncEstado.PcNoDisponible, is SyncEstado.Cortado, is SyncEstado.CuentaNoActiva -> Fase.ERROR
}

/** Título y detalle de lo que está pasando, en palabras del operario. */
private fun SincronizarUi.textos(): Pair<String, String> = when (val e = estado) {
    null -> when {
        buscando -> Textos.t("Buscando el PC…") to
            Textos.t("En el PC pulsa «Iniciar sincronización». Aparece como {pc}.", "pc" to PcConnector.NOMBRE_PC)
        pcDireccion == null -> Textos.t("Elige el PC") to
            Textos.t("Solo la primera vez hay que buscarlo; después conecta solo, sin claves ni códigos.")
        soloConectar -> Textos.t("Conecta con el PC") to
            Textos.t("Antes de iniciar sesión o registrarte, el teléfono debe estar conectado con el PC.")
        pendientes > 0 -> Textos.t("Listo para sincronizar") to
            Textos.n(pendientes, "{n} lectura por enviar.", "{n} lecturas por enviar.")
        else -> Textos.t("Listo para sincronizar") to
            Textos.t("No hay lecturas por enviar; se actualizará el catálogo.")
    }
    is SyncEstado.Conectando -> Textos.t("Conectando…") to
        Textos.t("Intento {i} de 3 · sin claves ni códigos.", "i" to e.intento)
    is SyncEstado.Sincronizando -> Textos.t("Enviando lecturas") to
        Textos.t("{n} de {m} confirmadas por el PC.", "n" to enviadas, "m" to porEnviar)
    is SyncEstado.Reintentando -> Textos.t("Reintentando…") to
        Textos.t("Se cortó la conexión. Intento {i} de 3.", "i" to e.intento)
    is SyncEstado.Listo -> if (soloConectar) Textos.t("¡Conectado!") to Textos.t("PC conectado. Ahora puedes iniciar sesión o registrarte.")
    else Textos.t("¡Listo!") to buildString {
        append(Textos.n(e.aceptados, "{n} lectura aceptada", "{n} lecturas aceptadas"))
        if (e.rechazados > 0) append(Textos.t(", {n} líneas reenviadas", "n" to e.rechazados))
        if (e.pendientes > 0) append(Textos.t(". Quedan {n} sin enviar: vuelve a sincronizar.", "n" to e.pendientes))
        else append(Textos.t(". Todo quedó en el PC."))
    }
    SyncEstado.Ocupado -> Textos.t("PC ocupado") to
        Textos.t("Está atendiendo a otro teléfono. Espera a que termine y vuelve a intentar.")
    is SyncEstado.Rechazado -> Textos.t("El PC rechazó la conexión") to e.motivo
    is SyncEstado.PcNoDisponible -> Textos.t("No se pudo conectar") to
        Textos.t("¿El PC está encendido, cerca y con la sincronización iniciada?")
    is SyncEstado.Cortado -> Textos.t("Se cortó la conexión") to
        Textos.t("Las {n} lecturas sin enviar siguen guardadas. Vuelve a intentar.", "n" to e.pendientes)
    is SyncEstado.CuentaNoActiva -> when (e.estado) {
        "PENDIENTE" -> Textos.t("Tu cuenta espera aprobación") to
            Textos.t("El administrador debe aprobarla en el PC. Tus {n} lecturas siguen guardadas.", "n" to e.pendientes)
        else -> Textos.t("Tu cuenta está {estado}", "estado" to Textos.estadoCuenta(e.estado)) to
            (e.motivo?.let { Textos.t("Motivo: {m}. ", "m" to it) } ?: "") +
            Textos.t("Tus {n} lecturas siguen guardadas.", "n" to e.pendientes)
    }
}

/**
 * Sincronizar (D22): con el PC ya elegido conecta de inmediato, sin emparejar ni códigos. La primera vez se busca
 * «gestion_inventario» y se elige. El indicador central cuenta lo que pasa: ondas al conectar, anillo al enviar, visto al terminar.
 */
@Composable
fun SincronizarScreen(
    ui: SincronizarUi,
    alSincronizar: () -> Unit,
    alBuscar: () -> Unit,
    alElegirPc: (direccion: String, nombre: String) -> Unit,
    alVolver: () -> Unit,
) {
    val fase = ui.fase()
    val enCurso = fase == Fase.RADAR && ui.estado != null || fase == Fase.PROGRESO
    val (titulo, detalle) = ui.textos()
    Pantalla(
        titulo = Textos.t(if (ui.soloConectar) "Conectar con el PC" else "Sincronizar"), subtitulo = Textos.t("Bluetooth · sin wifi"), alVolver = alVolver,
        barraInferior = {
            Button(onClick = alSincronizar, enabled = !enCurso && ui.pcDireccion != null, modifier = Modifier.fillMaxWidth().height(56.dp)) {
                Icon(Iconos.Sincronizar, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text(Textos.t(if (ui.soloConectar) (if (enCurso) "Conectando…" else "Conectar") else if (enCurso) "Sincronizando…" else "Sincronizar ahora"))
            }
        },
    ) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Indicador(fase, if (ui.porEnviar > 0) ui.enviadas.toFloat() / ui.porEnviar else 0f)
            AnimatedContent(titulo, transitionSpec = { fadeIn(tween(220)).togetherWith(fadeOut(tween(120))) }, label = "titulo") { t ->
                Text(t, style = MaterialTheme.typography.headlineSmall, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
            }
            Text(detalle, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
            AnimatedVisibility(ui.mensaje != null, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
                Surface(color = MaterialTheme.colorScheme.secondaryContainer, shape = MaterialTheme.shapes.medium) {
                    Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Info, contentDescription = null, tint = MaterialTheme.colorScheme.secondary)
                        Spacer(Modifier.width(10.dp))
                        Text(ui.mensaje.orEmpty(), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSecondaryContainer)
                    }
                }
            }
            TarjetaPc(ui, alBuscar)
            AnimatedVisibility(ui.buscando) { LinearProgressIndicator(Modifier.fillMaxWidth()) }
            ui.encontrados.forEachIndexed { i, (direccion, nombre) ->
                Entrada(i) {
                    Surface(onClick = { alElegirPc(direccion, nombre) }, shape = MaterialTheme.shapes.medium,
                        color = MaterialTheme.colorScheme.tertiaryContainer, modifier = Modifier.fillMaxWidth()) {
                        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                            IconoEnCirculo(Iconos.Bluetooth, MaterialTheme.colorScheme.tertiary, MaterialTheme.colorScheme.onTertiary, tam = 40)
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Text(nombre, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onTertiaryContainer)
                                Text(Textos.t("{direccion} · toca para conectar", "direccion" to direccion), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onTertiaryContainer)
                            }
                            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null, tint = MaterialTheme.colorScheme.onTertiaryContainer)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TarjetaPc(ui: SincronizarUi, alBuscar: () -> Unit) {
    Surface(shape = MaterialTheme.shapes.medium, color = MaterialTheme.colorScheme.surface, shadowElevation = 1.dp, modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(start = 14.dp, top = 10.dp, bottom = 10.dp, end = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            IconoEnCirculo(Iconos.Bluetooth, MaterialTheme.colorScheme.tertiaryContainer, MaterialTheme.colorScheme.tertiary, tam = 40)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(if (ui.pcDireccion == null) Textos.t("Sin PC elegido") else ui.pcNombre ?: PcConnector.NOMBRE_PC, style = MaterialTheme.typography.titleMedium)
                if (ui.pcDireccion == null) {
                    Text(Textos.t("Búscalo con el PC esperando"), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    Text(ui.pcDireccion, style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            if (ui.puedeCambiarPc) {
                TextButton(onClick = alBuscar, enabled = !ui.buscando) { Text(Textos.t(if (ui.pcDireccion == null) "Buscar" else "Cambiar")) }
            } else {
                Icon(Icons.Default.Lock, contentDescription = Textos.t("Cambiar el PC del teléfono"),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(end = 12.dp).size(18.dp))
            }
        }
    }
}

/** El indicador central: ondas mientras conecta o busca, anillo con porcentaje al enviar, y el resultado. */
@Composable
private fun Indicador(fase: Fase, progreso: Float) {
    val terciario = MaterialTheme.colorScheme.tertiary
    val primario = MaterialTheme.colorScheme.primary
    val pista = MaterialTheme.colorScheme.surfaceVariant
    val onda by rememberInfiniteTransition(label = "ondas").animateFloat(
        0f, 1f, infiniteRepeatable(tween(2200, easing = LinearEasing), RepeatMode.Restart), label = "t")
    val avance by animateFloatAsState(progreso.coerceIn(0f, 1f), tween(450), label = "avance")

    Box(Modifier.padding(top = 4.dp).size(232.dp), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val radio = size.minDimension / 2
            when (fase) {
                Fase.RADAR -> repeat(3) { i ->  // tres ondas desfasadas que crecen y se desvanecen
                    val f = (onda + i / 3f) % 1f
                    drawCircle(terciario.copy(alpha = (1f - f) * 0.30f), radius = radio * (0.45f + 0.55f * f))
                }
                Fase.PROGRESO -> {
                    val grosor = 14.dp.toPx()
                    val lado = size.minDimension - grosor - 16.dp.toPx()
                    val origen = Offset((size.width - lado) / 2, (size.height - lado) / 2)
                    drawArc(pista, 0f, 360f, false, origen, Size(lado, lado), style = Stroke(grosor))
                    drawArc(primario, -90f, 360f * avance, false, origen, Size(lado, lado), style = Stroke(grosor, cap = StrokeCap.Round))
                }
                else -> Unit
            }
        }
        AnimatedContent(
            fase,
            transitionSpec = {
                (scaleIn(spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessMediumLow), initialScale = 0.6f) + fadeIn())
                    .togetherWith(scaleOut(tween(150)) + fadeOut(tween(150)))
            },
            label = "fase",
        ) { f ->
            when (f) {
                Fase.REPOSO, Fase.RADAR -> IconoEnCirculo(Iconos.Bluetooth, terciario, MaterialTheme.colorScheme.onTertiary, tam = 104)
                Fase.PROGRESO -> Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("${(avance * 100).roundToInt()} %", style = MaterialTheme.typography.displayMedium.merge(Cifra), color = MaterialTheme.colorScheme.onSurface)
                    Text(Textos.t("enviado"), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Fase.LISTO -> IconoEnCirculo(Icons.Default.Check, Marca.Confirmado, Color.White, tam = 132)
                Fase.OCUPADO -> IconoEnCirculo(Icons.Default.Info, MaterialTheme.colorScheme.secondaryContainer, MaterialTheme.colorScheme.secondary, tam = 132)
                Fase.ERROR -> IconoEnCirculo(Icons.Default.Warning, MaterialTheme.colorScheme.errorContainer, MaterialTheme.colorScheme.error, tam = 132)
            }
        }
    }
}
