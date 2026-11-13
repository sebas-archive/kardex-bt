package co.edu.umariana.inventario.ui.pantallas

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ExitToApp
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import co.edu.umariana.inventario.auth.Rol
import co.edu.umariana.inventario.auth.Sesion
import co.edu.umariana.inventario.ui.componentes.Entrada
import co.edu.umariana.inventario.ui.componentes.Pantalla
import co.edu.umariana.inventario.ui.theme.Marca

data class PerfilUi(val cambiando: Boolean = false, val error: String? = null, val aviso: String? = null)

/** Mi cuenta: quién tiene la sesión abierta, su rol, cambiar la contraseña y cerrar sesión. */
@Composable
fun PerfilScreen(
    sesion: Sesion,
    ui: PerfilUi,
    alAbrirCambio: (Boolean) -> Unit,
    alCambiarClave: (actual: String, nueva: String, confirmacion: String) -> Unit,
    alCerrarSesion: () -> Unit,
    alVolver: () -> Unit,
) {
    var actual by rememberSaveable { mutableStateOf("") }
    var nueva by rememberSaveable { mutableStateOf("") }
    var confirmacion by rememberSaveable { mutableStateOf("") }

    Pantalla(titulo = "Mi cuenta", alVolver = alVolver) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Entrada(0) {
                Box(Modifier.size(112.dp).clip(CircleShape).background(Brush.linearGradient(listOf(Marca.Verde, Marca.VerdeProfundo))),
                    contentAlignment = Alignment.Center) {
                    Text(sesion.nombre.take(1).uppercase(), color = Color.White, style = MaterialTheme.typography.displayMedium)
                }
            }
            Entrada(1) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(sesion.nombre, style = MaterialTheme.typography.headlineSmall)
                    Text("@${sesion.usuario}", style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(Rol.nombre(sesion.rol), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onPrimaryContainer,
                        modifier = Modifier.clip(RoundedCornerShape(50)).background(MaterialTheme.colorScheme.primaryContainer).padding(horizontal = 14.dp, vertical = 6.dp))
                }
            }
            Entrada(2) {
                Surface(color = MaterialTheme.colorScheme.surface, shape = MaterialTheme.shapes.large, shadowElevation = 2.dp, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("Lo que puede hacer tu rol", style = MaterialTheme.typography.titleMedium)
                        Permiso("Contar y clasificar productos", true)
                        Permiso("Sincronizar con el PC configurado", true)
                        Permiso("Cambiar el PC del teléfono", true)
                    }
                }
            }
            Entrada(3) {
                Surface(color = MaterialTheme.colorScheme.surface, shape = MaterialTheme.shapes.large, shadowElevation = 2.dp, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.Lock, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                            Spacer(Modifier.width(10.dp))
                            Text("Contraseña", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                            TextButton(onClick = { alAbrirCambio(!ui.cambiando) }) { Text(if (ui.cambiando) "Cancelar" else "Cambiar") }
                        }
                        AnimatedVisibility(ui.aviso != null, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
                            Text(ui.aviso.orEmpty(), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary)
                        }
                        AnimatedVisibility(ui.cambiando, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
                            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                for ((etiqueta, valor, alCambiar) in listOf<Triple<String, String, (String) -> Unit>>(
                                    Triple("Contraseña actual", actual) { actual = it },
                                    Triple("Contraseña nueva", nueva) { nueva = it },
                                    Triple("Repite la contraseña nueva", confirmacion) { confirmacion = it },
                                )) {
                                    OutlinedTextField(
                                        value = valor, onValueChange = { if (it.length <= 64) alCambiar(it.replace("\n", "")) },
                                        label = { Text(etiqueta) }, singleLine = true, visualTransformation = PasswordVisualTransformation(),
                                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), modifier = Modifier.fillMaxWidth(),
                                    )
                                }
                                BarraFuerza(nueva)
                                AnimatedVisibility(ui.error != null) {
                                    Text(ui.error.orEmpty(), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error)
                                }
                                Button(onClick = { alCambiarClave(actual, nueva, confirmacion) }, modifier = Modifier.fillMaxWidth().height(50.dp)) {
                                    Text("Guardar contraseña")
                                }
                            }
                        }
                    }
                }
            }
            Entrada(4) {
                OutlinedButton(
                    onClick = alCerrarSesion, modifier = Modifier.fillMaxWidth().height(52.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error),
                ) {
                    Icon(Icons.AutoMirrored.Filled.ExitToApp, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("Cerrar sesión")
                }
            }
            Text("Las lecturas guardadas no se pierden al cerrar sesión.", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun Permiso(texto: String, permitido: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(if (permitido) Icons.Default.CheckCircle else Icons.Default.Warning, contentDescription = if (permitido) "Sí" else "No",
            tint = if (permitido) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(10.dp))
        Text(if (permitido) texto else "$texto (solo supervisor)", style = MaterialTheme.typography.bodyMedium,
            color = if (permitido) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
