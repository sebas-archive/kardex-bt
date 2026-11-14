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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import co.edu.umariana.inventario.data.NotificacionEntity
import co.edu.umariana.inventario.ui.Textos
import co.edu.umariana.inventario.ui.componentes.Entrada
import co.edu.umariana.inventario.ui.componentes.EstadoVacio
import co.edu.umariana.inventario.ui.componentes.IconoEnCirculo
import co.edu.umariana.inventario.ui.componentes.Pantalla
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

data class NotificacionesUi(
    val avisos: List<NotificacionEntity> = emptyList(),
    val soloSinLeer: Boolean = false,
)

/** Avisos del sistema: todas o sin leer, punto en las no leídas y «marcar todas». */
@Composable
fun NotificacionesScreen(
    ui: NotificacionesUi,
    alCambiarFiltro: (soloSinLeer: Boolean) -> Unit,
    alMarcarTodas: () -> Unit,
    alAbrir: (NotificacionEntity) -> Unit,
    alVolver: () -> Unit,
) {
    val visibles = if (ui.soloSinLeer) ui.avisos.filter { !it.leida } else ui.avisos
    val noLeidas = ui.avisos.count { !it.leida }
    Pantalla(
        titulo = Textos.t("Notificaciones"),
        subtitulo = Textos.n(noLeidas, "1 sin leer", "{n} sin leer"),
        alVolver = alVolver,
    ) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Filtro(Textos.t("Todas"), !ui.soloSinLeer) { alCambiarFiltro(false) }
            Filtro(Textos.t("Sin leer"), ui.soloSinLeer) { alCambiarFiltro(true) }
            Spacer(Modifier.weight(1f))
            if (noLeidas > 0) {
                TextButton(onClick = alMarcarTodas) {
                    Text(Textos.t("Marcar todas como leídas"), style = MaterialTheme.typography.labelMedium)
                }
            }
        }
        if (visibles.isEmpty()) {
            EstadoVacio(
                Icons.Default.Notifications,
                if (ui.soloSinLeer) Textos.t("No tienes avisos sin leer") else Textos.t("No hay notificaciones"),
                if (ui.soloSinLeer) Textos.t("No hay avisos en esta categoría.")
                else Textos.t("Aquí verás los avisos del sistema y de la sincronización."),
            )
        } else LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(visibles, key = { it.id }) { aviso ->
                Entrada(0) { FilaAviso(aviso) { alAbrir(aviso) } }
            }
        }
    }
}

@Composable
private fun Filtro(texto: String, activo: Boolean, alPulsar: () -> Unit) {
    Surface(
        onClick = alPulsar, shape = MaterialTheme.shapes.small,
        color = if (activo) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface,
        shadowElevation = if (activo) 0.dp else 1.dp,
    ) {
        Text(texto, Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            style = MaterialTheme.typography.labelLarge,
            color = if (activo) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun FilaAviso(aviso: NotificacionEntity, alPulsar: () -> Unit) {
    Surface(onClick = alPulsar, shape = MaterialTheme.shapes.medium, color = MaterialTheme.colorScheme.surface,
        shadowElevation = 1.dp, modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.Top) {
            IconoEnCirculo(Icons.Default.Notifications,
                if (aviso.leida) MaterialTheme.colorScheme.surfaceVariant else MaterialTheme.colorScheme.primaryContainer,
                if (aviso.leida) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.primary, tam = 40)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(Textos.tituloAviso(aviso), style = MaterialTheme.typography.titleMedium,
                        fontWeight = if (aviso.leida) FontWeight.Normal else FontWeight.SemiBold,
                        modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (!aviso.leida) {
                        Box(Modifier.size(9.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primary))
                    }
                }
                Text(Textos.detalleAviso(aviso), style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(
                    SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.getDefault()).format(Date(aviso.creadoMs)),
                    style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.outline,
                )
            }
        }
    }
}
