package com.sebasarchive.kardex.ui.pantallas

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.sebasarchive.kardex.data.TareaEntity
import com.sebasarchive.kardex.ui.componentes.Entrada
import com.sebasarchive.kardex.ui.componentes.EstadoVacio
import com.sebasarchive.kardex.ui.componentes.Iconos
import com.sebasarchive.kardex.ui.componentes.Pantalla

/** Una tarea tal como se muestra: [iniciada] si el operador ya la empezó en este teléfono. */
data class TareaFila(val tarea: TareaEntity, val iniciada: Boolean, val porRecontar: Int)

/** El estado que manda el PC, en palabras. */
val NOMBRE_ESTADO_TAREA = mapOf(
    "ASIGNADA" to "Asignada", "EN_PROGRESO" to "En progreso", "ENVIADA_PARCIALMENTE" to "Enviada parcialmente",
    "SINCRONIZADA" to "Sincronizada", "CON_DIFERENCIAS" to "Con diferencias", "CON_ERROR" to "Con error",
    "CERRADA" to "Cerrada",
)

/** «Mis tareas»: las tareas que el PC asignó a este operador (y los conteos generales). Tocar una la abre para contar. */
@Composable
fun TareasScreen(
    tareas: List<TareaFila>,
    actual: String?,
    alIniciar: (id: String) -> Unit,
    alVolver: () -> Unit,
    alSincronizar: () -> Unit,
) {
    Pantalla(titulo = "Mis tareas", subtitulo = "Lo que te asignaron para contar", alVolver = alVolver) {
        if (tareas.isEmpty()) {
            EstadoVacio(Iconos.Caja, "No tienes tareas asignadas",
                "Cuando Inventario te asigne una, aparecerá aquí después de sincronizar con el PC.") {
                Button(onClick = alSincronizar) { Text("Sincronizar con el PC") }
            }
        } else Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Se actualizan cada vez que sincronizas", style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            tareas.forEachIndexed { i, fila ->
                Entrada(i) { TarjetaTarea(fila, actual = fila.tarea.id == actual) { alIniciar(fila.tarea.id) } }
            }
        }
    }
}

@Composable
private fun TarjetaTarea(fila: TareaFila, actual: Boolean, alIniciar: () -> Unit) {
    val t = fila.tarea
    val colores = MaterialTheme.colorScheme
    Surface(
        shape = MaterialTheme.shapes.medium, color = if (actual) colores.primaryContainer else colores.surface,
        border = BorderStroke(if (actual) 2.dp else 1.dp, if (actual) colores.primary else colores.outlineVariant),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            val cabecera = if (t.esGeneral) "${t.id} · Conteo general"
            else listOf(t.id, t.almacen, "${t.contados}/${t.total}", NOMBRE_ESTADO_TAREA[t.estado] ?: t.estado).joinToString(" · ")
            Text(cabecera, style = MaterialTheme.typography.labelLarge, color = colores.primary)
            Text(t.nombre, style = MaterialTheme.typography.titleMedium)
            if (t.instrucciones.isNotBlank()) {
                Text("“${t.instrucciones}”", style = MaterialTheme.typography.bodyMedium, color = colores.onSurfaceVariant)
            }
            if (!t.esGeneral && t.total > 0) {
                LinearProgressIndicator(progress = { t.contados.toFloat() / t.total }, modifier = Modifier.fillMaxWidth())
            }
            if (fila.porRecontar > 0) {
                Text(if (fila.porRecontar == 1) "1 producto por recontar" else "${fila.porRecontar} productos por recontar",
                    style = MaterialTheme.typography.bodyMedium, color = colores.error)
            }
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Spacer(Modifier.weight(1f))
                FilledTonalButton(onClick = alIniciar, modifier = Modifier.height(44.dp)) {
                    Text(if (fila.iniciada || actual) "Continuar" else "Iniciar")
                }
            }
        }
    }
}
