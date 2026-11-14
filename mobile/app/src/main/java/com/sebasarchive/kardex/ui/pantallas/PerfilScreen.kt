package com.sebasarchive.kardex.ui.pantallas

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
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
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ExitToApp
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.sebasarchive.kardex.auth.Sesion
import com.sebasarchive.kardex.ui.SettingsStore
import com.sebasarchive.kardex.ui.Textos
import com.sebasarchive.kardex.ui.componentes.Entrada
import com.sebasarchive.kardex.ui.componentes.Pantalla
import com.sebasarchive.kardex.ui.theme.Marca

data class PerfilUi(
    val foto: String? = null,
    val correo: String? = null,
    val tema: String = SettingsStore.TEMA_SISTEMA,
    val idioma: String = "es",
    val error: String? = null,
    val aviso: String? = null,
)

/**
 * Mi cuenta: foto de perfil, datos, tema, idioma y cerrar sesión. No cambia la contraseña: el Operador la
 * recupera desde Acceso con su pregunta de seguridad.
 */
@Composable
fun PerfilScreen(
    sesion: Sesion,
    ui: PerfilUi,
    alPonerFoto: () -> Unit,
    alEliminarFoto: () -> Unit,
    alCambiarTema: (String) -> Unit,
    alCambiarIdioma: (String) -> Unit,
    alCerrarSesion: () -> Unit,
    alVolver: () -> Unit,
) {
    var confirmarBorrado by remember { mutableStateOf(false) }

    Pantalla(titulo = Textos.t("Mi cuenta"), alVolver = alVolver) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Entrada(0) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    FotoPerfil(ui.foto, sesion.nombre)
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedButton(onClick = alPonerFoto) {
                            Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(6.dp))
                            Text(Textos.t(if (ui.foto == null) "Poner foto" else "Cambiar foto"))
                        }
                        if (ui.foto != null) {
                            TextButton(onClick = { confirmarBorrado = true },
                                colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error)) {
                                Icon(Icons.Default.Delete, contentDescription = null, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.width(6.dp))
                                Text(Textos.t("Eliminar foto"))
                            }
                        }
                    }
                    if (ui.error != null) {
                        Text(ui.error, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error,
                            textAlign = TextAlign.Center)
                    }
                }
            }
            Entrada(1) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(sesion.nombre, style = MaterialTheme.typography.headlineSmall)
                    Text("@${sesion.usuario}", style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    ui.correo?.let {
                        Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Text(Textos.rol(sesion.rol), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onPrimaryContainer,
                        modifier = Modifier.clip(RoundedCornerShape(50)).background(MaterialTheme.colorScheme.primaryContainer).padding(horizontal = 14.dp, vertical = 6.dp))
                }
            }
            Entrada(2) {
                Tarjeta(Textos.t("Preferencias"), Icons.Default.Settings) {
                    Text(Textos.t("Tema"), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (tema in SettingsStore.TEMAS) {
                            FilterChip(selected = ui.tema == tema, onClick = { alCambiarTema(tema) },
                                label = { Text(Textos.tema(tema)) }, modifier = Modifier.weight(1f))
                        }
                    }
                    Spacer(Modifier.height(6.dp))
                    Text(Textos.t("Idioma"), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (idioma in listOf("es", "en")) {
                            FilterChip(selected = ui.idioma == idioma, onClick = { alCambiarIdioma(idioma) },
                                label = { Text(Textos.idiomaNombre(idioma)) }, modifier = Modifier.weight(1f))
                        }
                    }
                }
            }
            Entrada(3) {
                Tarjeta(Textos.t("Lo que puede hacer tu rol"), Icons.Default.Person) {
                    Permiso(Textos.t("Contar productos"), true)
                    Permiso(Textos.t("Sincronizar con el PC configurado"), true)
                    Permiso(Textos.t("Cambiar el PC del teléfono"), true)
                }
            }
            Entrada(4) {
                OutlinedButton(
                    onClick = alCerrarSesion, modifier = Modifier.fillMaxWidth().height(52.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error),
                ) {
                    Icon(Icons.AutoMirrored.Filled.ExitToApp, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text(Textos.t("Cerrar sesión"))
                }
            }
            Text(Textos.t("Las lecturas guardadas no se pierden al cerrar sesión."), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }

    if (confirmarBorrado) {
        AlertDialog(
            onDismissRequest = { confirmarBorrado = false },
            title = { Text(Textos.t("¿Eliminar la foto de perfil?")) },
            text = { Text(Textos.t("Se perderá la foto actual y volverá a mostrarse tu inicial.")) },
            confirmButton = {
                TextButton(onClick = { confirmarBorrado = false; alEliminarFoto() }) { Text(Textos.t("Eliminar")) }
            },
            dismissButton = { TextButton(onClick = { confirmarBorrado = false }) { Text(Textos.t("Cancelar")) } },
        )
    }
}

@Composable
private fun FotoPerfil(foto: String?, nombre: String) {
    val imagen = remember(foto) { foto?.let { BitmapFactory.decodeFile(it)?.asImageBitmap() } }
    Box(
        Modifier.size(116.dp).clip(CircleShape)
            .background(if (imagen == null) Brush.linearGradient(listOf(Marca.Verde, Marca.VerdeProfundo)) else Brush.linearGradient(listOf(Color.Transparent, Color.Transparent))),
        contentAlignment = Alignment.Center,
    ) {
        if (imagen != null) {
            Image(imagen, contentDescription = Textos.t("Foto de perfil"), contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize().clip(CircleShape))
        } else {
            Text(nombre.take(1).uppercase(), color = Color.White, style = MaterialTheme.typography.displayMedium)
        }
    }
}

@Composable
private fun Tarjeta(titulo: String, icono: androidx.compose.ui.graphics.vector.ImageVector, contenido: @Composable () -> Unit) {
    Surface(color = MaterialTheme.colorScheme.surface, shape = MaterialTheme.shapes.large, shadowElevation = 2.dp,
        modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(icono, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(10.dp))
                Text(titulo, style = MaterialTheme.typography.titleMedium)
            }
            contenido()
        }
    }
}

@Composable
private fun Permiso(texto: String, permitido: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(if (permitido) Icons.Default.CheckCircle else Icons.Default.Warning,
            contentDescription = Textos.t(if (permitido) "Sí" else "No"),
            tint = if (permitido) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline,
            modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(10.dp))
        Text(texto, style = MaterialTheme.typography.bodyMedium,
            color = if (permitido) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
