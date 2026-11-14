package co.edu.umariana.inventario.ui

import android.content.Intent
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.Composable
import co.edu.umariana.inventario.R
import co.edu.umariana.inventario.auth.AuthResult
import co.edu.umariana.inventario.ui.theme.InventarioTheme

/** Cómo llega una pantalla (y, al volver, cómo se va: por donde vino). */
enum class Transicion(val entra: Int, val sale: Int, val vuelveEntra: Int, val vuelveSale: Int) {
    /** Avanzar en el flujo: llega desde la derecha creciendo mientras la anterior se aleja. */
    LATERAL(R.anim.entra_derecha, R.anim.sale_izquierda, R.anim.entra_izquierda, R.anim.sale_derecha),
    /** Una tarea aparte (Sincronizar, Mi cuenta): sube como una hoja y la de atrás se hunde. */
    HOJA(R.anim.entra_abajo, R.anim.sale_fondo, R.anim.entra_fondo, R.anim.sale_abajo),
    /** Cambio de contexto (entrar o salir de la sesión): fundido con zoom. */
    FUNDIDO(R.anim.aparece, R.anim.desaparece, R.anim.aparece, R.anim.desaparece),
}

/**
 * Base de las pantallas: cada Activity dibuja su contenido con Compose dentro del tema de la app y entra con una
 * [Transicion]; al cerrarse hace la misma en sentido contrario.
 */
abstract class PantallaActivity : ComponentActivity() {
    protected fun pantalla(contenido: @Composable () -> Unit) = setContent { InventarioTheme { contenido() } }

    @Suppress("DEPRECATION")  // overridePendingTransition: su reemplazo (overrideActivityTransition) solo existe desde Android 14
    protected fun abrir(destino: Class<*>, transicion: Transicion = Transicion.LATERAL, configurar: Intent.() -> Unit = {}) {
        startActivity(Intent(this, destino).putExtra(EXTRA_TRANSICION, transicion.name).apply(configurar))
        overridePendingTransition(transicion.entra, transicion.sale)
    }

    /** Abre [destino] como única pantalla de la app (tras entrar o cerrar sesión), con un fundido. */
    @Suppress("DEPRECATION")
    protected fun reemplazarPor(destino: Class<*>) {
        startActivity(Intent(this, destino).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        overridePendingTransition(Transicion.FUNDIDO.entra, Transicion.FUNDIDO.sale)
    }

    @Suppress("DEPRECATION")
    override fun finish() {
        super.finish()
        val transicion = runCatching { Transicion.valueOf(intent.getStringExtra(EXTRA_TRANSICION).orEmpty()) }.getOrNull() ?: return
        overridePendingTransition(transicion.vuelveEntra, transicion.vuelveSale)
    }

    protected fun aviso(mensaje: String) = Toast.makeText(this, mensaje, Toast.LENGTH_LONG).show()

    private companion object {
        const val EXTRA_TRANSICION = "transicion"
    }
}

/** El mensaje que ve el operario cuando no se pudo guardar. */
fun SaveResult.mensaje(): String = when (this) {
    is SaveResult.Guardada -> if (reemplazo) "Recuento guardado: reemplaza la lectura anterior" else "Guardado"
    SaveResult.OperadorFaltante -> "Inicia sesión de nuevo: falta el nombre del operador"
    SaveResult.SinConteo -> "Elige primero el conteo"
    SaveResult.SkuFaltante -> "Escanea o escribe el SKU"
    SaveResult.CantidadInvalida -> "Cantidad inválida: usa números con punto decimal (hasta 9 enteros y 3 decimales)"
    SaveResult.NotaLarga -> "La nota admite hasta ${CountViewModel.MAX_NOTA} caracteres"
    SaveResult.DanadosInvalidos -> "Los dañados deben ser un número (punto decimal) y no más que la cantidad"
}

/** El mensaje de cada resultado de acceso que no es un éxito. */
fun AuthResult.mensaje(): String = when (this) {
    is AuthResult.Ok -> ""
    AuthResult.UsuarioInvalido -> "El usuario debe tener de 3 a 20 caracteres: letras, números, punto o guion"
    AuthResult.NombreInvalido -> "Escribe tu nombre completo (máximo 60 caracteres)"
    AuthResult.ClaveDebil -> "La contraseña necesita mínimo 8 caracteres, con letras y números"
    AuthResult.ClavesDistintas -> "Las dos contraseñas no coinciden"
    AuthResult.PreguntaFaltante -> "Elige una pregunta de seguridad"
    AuthResult.RespuestaCorta -> "Escribe la respuesta a la pregunta de seguridad"
    AuthResult.UsuarioExiste -> "Ese usuario ya existe en este teléfono"
    AuthResult.CredencialesInvalidas -> "Usuario o contraseña incorrectos"
    is AuthResult.Bloqueado -> "Demasiados intentos. Espera $segundos segundos y vuelve a probar"
    AuthResult.UsuarioNoExiste -> "No hay una cuenta con ese usuario en este teléfono"
    AuthResult.RespuestaIncorrecta -> "La respuesta no coincide"
    AuthResult.SinSesion -> "No hay una sesión abierta"
}
