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
    /** Carga el tema y el idioma del usuario de la sesión antes de dibujar: cada pantalla respeta su preferencia. */
    protected fun pantalla(contenido: @Composable () -> Unit) =
        pantallaPara(Servicios.de(this).auth.sesion()?.usuario, contenido)

    /** Igual que [pantalla], pero con un usuario explícito; `null` = invitado (Acceso y Estado de cuenta). */
    protected fun pantallaPara(usuarioApariencia: String?, contenido: @Composable () -> Unit) {
        val servicios = Servicios.de(this)
        Apariencia.cargar(servicios.settings, usuarioApariencia)
        setContent { InventarioTheme { contenido() } }
    }

    @Suppress("DEPRECATION")  // overridePendingTransition: su reemplazo (overrideActivityTransition) solo existe desde Android 14
    protected fun abrir(destino: Class<*>, transicion: Transicion = Transicion.LATERAL, configurar: Intent.() -> Unit = {}) {
        startActivity(Intent(this, destino).putExtra(EXTRA_TRANSICION, transicion.name).apply(configurar))
        overridePendingTransition(transicion.entra, transicion.sale)
    }

    /** Abre [destino] como única pantalla de la app (tras entrar o cerrar sesión), con un fundido. */
    @Suppress("DEPRECATION")
    protected fun reemplazarPor(destino: Class<*>, configurar: Intent.() -> Unit = {}) {
        startActivity(Intent(this, destino).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK).apply(configurar))
        overridePendingTransition(Transicion.FUNDIDO.entra, Transicion.FUNDIDO.sale)
    }

    @Suppress("DEPRECATION")
    override fun finish() {
        super.finish()
        val transicion = runCatching { Transicion.valueOf(intent.getStringExtra(EXTRA_TRANSICION).orEmpty()) }.getOrNull() ?: return
        overridePendingTransition(transicion.vuelveEntra, transicion.vuelveSale)
    }

    protected fun aviso(mensaje: String) = Toast.makeText(this, Textos.t(mensaje), Toast.LENGTH_LONG).show()

    private companion object {
        const val EXTRA_TRANSICION = "transicion"
    }
}

/** El mensaje que ve el operario cuando no se pudo guardar. */
fun SaveResult.mensaje(): String = when (this) {
    is SaveResult.Guardada -> if (reemplazo) Textos.t("Recuento guardado: reemplaza la lectura anterior") else Textos.t("Guardado")
    SaveResult.OperadorFaltante -> Textos.t("Inicia sesión de nuevo: falta el nombre del operador")
    SaveResult.SkuFaltante -> Textos.t("Escanea o escribe el SKU")
    SaveResult.CantidadInvalida -> Textos.t("Cantidad inválida: usa números con punto decimal (hasta 9 enteros y 3 decimales)")
    SaveResult.NotaLarga -> Textos.t("La nota admite hasta {n} caracteres", "n" to CountViewModel.MAX_NOTA)
    SaveResult.DanadosInvalidos -> Textos.t("Los dañados deben ser un número (punto decimal) y no más que la cantidad")
}

/** El mensaje de cada resultado de acceso que no es un éxito. */
fun AuthResult.mensaje(): String = when (this) {
    is AuthResult.Ok -> ""
    AuthResult.UsuarioInvalido -> Textos.t("El usuario debe tener de 3 a 20 caracteres: letras, números, punto o guion")
    AuthResult.NombreInvalido -> Textos.t("Escribe tu nombre completo (máximo 60 caracteres)")
    AuthResult.CorreoInvalido -> Textos.t("Escribe un correo válido (máximo 120 caracteres)")
    AuthResult.ClaveDebil -> Textos.t("La contraseña necesita mínimo 8 caracteres, con letras y números")
    AuthResult.ClavesDistintas -> Textos.t("Las dos contraseñas no coinciden")
    AuthResult.PreguntaFaltante -> Textos.t("Elige una pregunta de seguridad")
    AuthResult.RespuestaCorta -> Textos.t("Escribe la respuesta a la pregunta de seguridad")
    AuthResult.UsuarioExiste -> Textos.t("Ese usuario ya existe en este teléfono")
    AuthResult.CredencialesInvalidas -> Textos.t("Usuario o contraseña incorrectos")
    is AuthResult.Bloqueado -> Textos.t("Demasiados intentos. Espera {n} segundos y vuelve a probar", "n" to segundos)
    AuthResult.UsuarioNoExiste -> Textos.t("No hay una cuenta con ese usuario en este teléfono")
    AuthResult.RespuestaIncorrecta -> Textos.t("La respuesta no coincide")
}
