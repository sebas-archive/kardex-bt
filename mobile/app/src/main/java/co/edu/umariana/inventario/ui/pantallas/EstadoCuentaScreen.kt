package co.edu.umariana.inventario.ui.pantallas

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import co.edu.umariana.inventario.auth.EstadoCuenta
import co.edu.umariana.inventario.ui.Textos
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Lo que muestra la pantalla de una cuenta que no puede trabajar. */
data class EstadoCuentaUi(
    val nombre: String,
    val usuario: String,
    val estado: String,
    val motivo: String?,
    val registradoMs: Long?,
)

fun mensajeEstado(estado: String): String = Textos.t(when (estado) {
    EstadoCuenta.PENDIENTE -> "Tu cuenta espera aprobación del administrador"
    EstadoCuenta.RECHAZADO -> "El administrador rechazó tu solicitud de cuenta"
    EstadoCuenta.SUSPENDIDO -> "El administrador suspendió tu cuenta"
    else -> ""
})

/** El botón principal: con la cuenta pendiente hay sesión que cerrar; rechazada o suspendida, se vuelve al acceso. */
fun textoBotonEstado(estado: String): String =
    Textos.t(if (estado == EstadoCuenta.PENDIENTE) "Cerrar sesión" else "Regresar al inicio de sesión")

/**
 * Cuenta PENDIENTE, RECHAZADO o SUSPENDIDO: el operador no entra a contar. «Comprobar estado» sincroniza con el PC
 * para enterarse de una aprobación o reactivación (una cuenta rechazada no cambia, así que no lo ofrece).
 */
@Composable
fun EstadoCuentaScreen(ui: EstadoCuentaUi, alComprobar: () -> Unit, alSalir: () -> Unit) {
    val color = if (ui.estado == EstadoCuenta.PENDIENTE) Color(0xFFB7791F) else MaterialTheme.colorScheme.error
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.Start,
    ) {
        Text(Textos.t("Inventario"), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(16.dp))
        Text(ui.nombre, style = MaterialTheme.typography.titleLarge)
        Text("@${ui.usuario}", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(16.dp))
        Surface(shape = MaterialTheme.shapes.small, border = BorderStroke(1.dp, color), color = Color.Transparent) {
            Text(Textos.estadoCuenta(ui.estado), color = color, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(horizontal = 10.dp, vertical = 2.dp))
        }
        Spacer(Modifier.height(12.dp))
        Text(mensajeEstado(ui.estado), style = MaterialTheme.typography.bodyLarge)
        if (ui.estado != EstadoCuenta.PENDIENTE && !ui.motivo.isNullOrBlank()) {
            Spacer(Modifier.height(8.dp))
            Text(Textos.t("Motivo: {m}", "m" to ui.motivo), style = MaterialTheme.typography.bodyLarge)
        }
        ui.registradoMs?.let {
            Spacer(Modifier.height(8.dp))
            Text(Textos.t("Registrada el {fecha}", "fecha" to SimpleDateFormat("dd/MM/yyyy", Locale.getDefault()).format(Date(it))),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Spacer(Modifier.height(24.dp))
        Button(onClick = alSalir, modifier = Modifier.fillMaxWidth().height(50.dp)) { Text(textoBotonEstado(ui.estado)) }
        if (ui.estado != EstadoCuenta.RECHAZADO) {
            TextButton(onClick = alComprobar, modifier = Modifier.fillMaxWidth()) { Text(Textos.t("Comprobar estado")) }
        }
    }
}
