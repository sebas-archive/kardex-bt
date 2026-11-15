package com.sebasarchive.kardex.ui.componentes

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.sebasarchive.kardex.ui.Apariencia
import com.sebasarchive.kardex.ui.Servicios
import com.sebasarchive.kardex.ui.SettingsStore
import com.sebasarchive.kardex.ui.Textos

/**
 * Acceso rápido a tema e idioma desde cualquier pantalla. Guarda la preferencia del usuario en curso
 * ([Apariencia.usuarioActual]; `null` = invitado en Acceso y Estado de cuenta) y se aplica al instante.
 */
@Composable
fun BotonApariencia(
    modifier: Modifier = Modifier,
    tinte: Color = MaterialTheme.colorScheme.onSurfaceVariant,
) {
    val context = LocalContext.current
    val servicios = remember(context) { Servicios.de(context) }
    var abierto by remember { mutableStateOf(false) }

    IconButton(onClick = { abierto = true }, modifier = modifier) {
        Icon(Icons.Default.Settings, contentDescription = Textos.t("Apariencia"), tint = tinte)
    }

    if (abierto) {
        AlertDialog(
            onDismissRequest = { abierto = false },
            title = { Text(Textos.t("Apariencia")) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(Textos.t("Tema"), style = MaterialTheme.typography.labelLarge)
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        for (tema in SettingsStore.TEMAS) {
                            FilterChip(
                                selected = Apariencia.tema == tema,
                                onClick = {
                                    Apariencia.cambiarTema(servicios.settings, Apariencia.usuarioActual, tema)
                                    abierto = false
                                },
                                label = { Text(Textos.tema(tema)) },
                            )
                        }
                    }
                    Text(Textos.t("Idioma"), style = MaterialTheme.typography.labelLarge)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (idioma in listOf("es", "en")) {
                            FilterChip(
                                selected = Apariencia.idioma == idioma,
                                onClick = {
                                    Apariencia.cambiarIdioma(servicios.settings, Apariencia.usuarioActual, idioma)
                                    abierto = false
                                },
                                label = { Text(Textos.idiomaNombre(idioma)) },
                            )
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { abierto = false }) { Text(Textos.t("Cancelar")) }
            },
        )
    }
}
