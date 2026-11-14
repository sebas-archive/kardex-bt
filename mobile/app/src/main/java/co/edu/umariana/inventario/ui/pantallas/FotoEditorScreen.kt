package co.edu.umariana.inventario.ui.pantallas

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTransformGestures
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
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import co.edu.umariana.inventario.ui.Textos
import co.edu.umariana.inventario.ui.componentes.Pantalla
import kotlin.math.roundToInt

/**
 * Editor de la foto de perfil: rotar, zoom, encuadre arrastrando y vista previa cuadrada/circular.
 * El cuadrado visible es el recorte que se guarda.
 */
@Composable
fun FotoEditorScreen(
    imagen: Bitmap,
    alGuardar: (rotacion: Int, zoom: Float, panX: Float, panY: Float) -> Unit,
    alCancelar: () -> Unit,
) {
    var rotacion by remember { mutableIntStateOf(0) }
    var zoom by remember { mutableFloatStateOf(1f) }
    var desplazamiento by remember { mutableStateOf(Offset.Zero) }
    var lado by remember { mutableFloatStateOf(1f) }
    val bitmap = remember(imagen) { imagen.asImageBitmap() }

    Pantalla(
        titulo = Textos.t("Editar foto"),
        alVolver = alCancelar,
        barraInferior = {
            Button(
                onClick = {
                    val medio = (lado / 2f).coerceAtLeast(1f)
                    alGuardar(
                        rotacion,
                        zoom,
                        (desplazamiento.x / medio).coerceIn(-1f, 1f),
                        (desplazamiento.y / medio).coerceIn(-1f, 1f),
                    )
                },
                modifier = Modifier.fillMaxWidth().height(54.dp),
            ) {
                Icon(Icons.Default.Check, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text(Textos.t("Guardar"))
            }
        },
    ) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(Textos.t("Arrastra para encuadrar"), style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(18.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier.size(260.dp).clip(RoundedCornerShape(24.dp)).background(Color.Black)
                        .onSizeChanged { lado = it.width.toFloat() }
                        .pointerInput(Unit) {
                            detectTransformGestures { _, pan, zoomCambio, _ ->
                                zoom = (zoom * zoomCambio).coerceIn(1f, 4f)
                                desplazamiento += pan
                            }
                        },
                    contentAlignment = Alignment.Center,
                ) {
                    Image(
                        bitmap, contentDescription = Textos.t("Vista previa"), contentScale = ContentScale.Crop,
                        modifier = Modifier.fillMaxSize().graphicsLayer {
                            rotationZ = rotacion.toFloat()
                            scaleX = zoom
                            scaleY = zoom
                            translationX = desplazamiento.x
                            translationY = desplazamiento.y
                        },
                    )
                    // Marco del recorte.
                    Box(Modifier.fillMaxSize().padding(10.dp).clip(RoundedCornerShape(16.dp))
                        .background(Color.Transparent))
                    Text(
                        Textos.t("Cortar"), color = Color.White, style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.align(Alignment.TopStart).padding(10.dp)
                            .clip(RoundedCornerShape(50)).background(Color.Black.copy(alpha = 0.55f))
                            .padding(horizontal = 8.dp, vertical = 4.dp),
                    )
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Box(Modifier.size(92.dp).clip(CircleShape).background(Color.Black), contentAlignment = Alignment.Center) {
                        Image(
                            bitmap, contentDescription = null, contentScale = ContentScale.Crop,
                            modifier = Modifier.fillMaxSize().graphicsLayer {
                                rotationZ = rotacion.toFloat()
                                scaleX = zoom
                                scaleY = zoom
                                translationX = desplazamiento.x / 2
                                translationY = desplazamiento.y / 2
                            },
                        )
                    }
                    Text(Textos.t("Vista previa"), style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(onClick = { rotacion = (rotacion + 90) % 360 }, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(Textos.t("Rotar"))
                }
                Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = MaterialTheme.shapes.small,
                    modifier = Modifier.weight(1f)) {
                    Column(Modifier.padding(horizontal = 12.dp, vertical = 6.dp)) {
                        Text(Textos.t("Zoom"), style = MaterialTheme.typography.labelSmall)
                        Slider(value = zoom, onValueChange = { zoom = it }, valueRange = 1f..4f,
                            colors = SliderDefaults.colors(inactiveTrackColor = MaterialTheme.colorScheme.outlineVariant))
                    }
                }
            }
            Text(Textos.t("Se guardará un cuadrado; el avatar se muestra circular."),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center)
        }
    }
}
