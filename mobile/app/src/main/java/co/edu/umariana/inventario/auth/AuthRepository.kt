package co.edu.umariana.inventario.auth

import co.edu.umariana.inventario.ui.SettingsStore
import kotlin.math.ceil

/**
 * Quién tiene la sesión abierta en el teléfono y en qué estado está su cuenta. Solo con [puedeTrabajar] entra al
 * inicio; con otro estado la app muestra la pantalla de su estado (pendiente, rechazada o suspendida).
 */
data class Sesion(
    val usuario: String,
    val nombre: String,
    val rol: String,
    val estado: String = EstadoCuenta.ACTIVO,
    val motivo: String? = null,
) {
    val puedeTrabajar: Boolean get() = estado == EstadoCuenta.ACTIVO
}

sealed class AuthResult {
    data class Ok(val usuario: UsuarioEntity) : AuthResult()
    data object UsuarioInvalido : AuthResult()
    data object NombreInvalido : AuthResult()
    data object ClaveDebil : AuthResult()
    data object ClavesDistintas : AuthResult()
    data object PreguntaFaltante : AuthResult()
    data object RespuestaCorta : AuthResult()
    data object UsuarioExiste : AuthResult()
    /** Usuario o contraseña incorrectos: el mismo resultado para ambos, para no revelar qué cuentas existen. */
    data object CredencialesInvalidas : AuthResult()
    /** Demasiados intentos fallidos: hay que esperar [segundos]. */
    data class Bloqueado(val segundos: Int) : AuthResult()
    data object UsuarioNoExiste : AuthResult()
    data object RespuestaIncorrecta : AuthResult()
    data object SinSesion : AuthResult()
}

/**
 * Cuentas del teléfono: registro, inicio de sesión, recuperación de contraseña y cierre de sesión.
 *
 * La contraseña es **local**: la app trabaja sin red, así que no hay servidor que la valide ni correo al que escribir.
 * La contraseña olvidada se recupera con la respuesta a una pregunta de seguridad elegida al registrarse. Tras
 * [MAX_INTENTOS] fallos seguidos (de contraseña o de respuesta) la cuenta se bloquea [BLOQUEO_MS].
 *
 * El **estado** de la cuenta lo decide el administrador en el PC: una cuenta nueva queda PENDIENTE y el teléfono
 * aprende su estado al sincronizar ([aplicarEstado]).
 *
 * Las funciones derivan claves (lento a propósito) y tocan Room: se llaman fuera del hilo de la interfaz.
 */
class AuthRepository(
    private val dao: UsuarioDao,
    private val settings: SettingsStore,
    private val ahoraMs: () -> Long = System::currentTimeMillis,
    private val iteraciones: Int = Claves.ITERACIONES,
) {
    fun registrar(
        usuario: String, nombre: String, clave: String, confirmacion: String,
        pregunta: String, respuesta: String,
    ): AuthResult {
        val alias = normalizar(usuario)
        val nombreLimpio = nombre.trim()
        if (!USUARIO.matches(alias)) return AuthResult.UsuarioInvalido
        if (nombreLimpio.isEmpty() || nombreLimpio.codePointCount(0, nombreLimpio.length) > MAX_NOMBRE) return AuthResult.NombreInvalido
        validarClave(clave, confirmacion)?.let { return it }
        if (pregunta.isBlank()) return AuthResult.PreguntaFaltante
        if (normalizarRespuesta(respuesta).length < 2) return AuthResult.RespuestaCorta
        if (dao.porUsuario(alias) != null) return AuthResult.UsuarioExiste

        val nuevo = UsuarioEntity(
            usuario = alias, nombre = nombreLimpio, rol = Rol.OPERADOR, estado = EstadoCuenta.PENDIENTE,
            claveHash = Claves.crear(clave, iteraciones), pregunta = pregunta.trim(),
            respuestaHash = Claves.crear(normalizarRespuesta(respuesta), iteraciones), creadoMs = ahoraMs(),
        )
        val guardado = nuevo.copy(id = dao.insertar(nuevo))
        abrirSesion(guardado)
        return AuthResult.Ok(guardado)
    }

    fun iniciarSesion(usuario: String, clave: String): AuthResult {
        val cuenta = dao.porUsuario(normalizar(usuario)) ?: return AuthResult.CredencialesInvalidas
        bloqueo(cuenta)?.let { return it }
        if (!Claves.verificar(clave, cuenta.claveHash)) return fallo(cuenta, AuthResult.CredencialesInvalidas)
        val limpia = cuenta.copy(intentosFallidos = 0, bloqueadoHastaMs = 0)
        dao.actualizar(limpia)
        abrirSesion(limpia)
        return AuthResult.Ok(limpia)
    }

    /** La pregunta de seguridad de esa cuenta, o null si no existe. */
    fun preguntaDe(usuario: String): String? = dao.porUsuario(normalizar(usuario))?.pregunta

    /** Cambia la contraseña con la respuesta de seguridad. No abre sesión: después se entra con la clave nueva. */
    fun restablecer(usuario: String, respuesta: String, clave: String, confirmacion: String): AuthResult {
        val cuenta = dao.porUsuario(normalizar(usuario)) ?: return AuthResult.UsuarioNoExiste
        bloqueo(cuenta)?.let { return it }
        if (!Claves.verificar(normalizarRespuesta(respuesta), cuenta.respuestaHash)) return fallo(cuenta, AuthResult.RespuestaIncorrecta)
        val sinFallos = cuenta.copy(intentosFallidos = 0, bloqueadoHastaMs = 0)
        dao.actualizar(sinFallos)
        validarClave(clave, confirmacion)?.let { return it }
        val actualizada = sinFallos.copy(claveHash = Claves.crear(clave, iteraciones))
        dao.actualizar(actualizada)
        return AuthResult.Ok(actualizada)
    }

    /** Cambia la contraseña de quien tiene la sesión abierta; exige la actual. */
    fun cambiarClave(actual: String, nueva: String, confirmacion: String): AuthResult {
        val sesion = sesion() ?: return AuthResult.SinSesion
        val cuenta = dao.porUsuario(sesion.usuario) ?: return AuthResult.SinSesion
        if (!Claves.verificar(actual, cuenta.claveHash)) return AuthResult.CredencialesInvalidas
        validarClave(nueva, confirmacion)?.let { return it }
        val actualizada = cuenta.copy(claveHash = Claves.crear(nueva, iteraciones))
        dao.actualizar(actualizada)
        return AuthResult.Ok(actualizada)
    }

    fun sesion(): Sesion? {
        val usuario = settings.sesionUsuario ?: return null
        return Sesion(usuario, settings.sesionNombre.orEmpty(), settings.sesionRol ?: Rol.OPERADOR,
            settings.sesionEstado ?: EstadoCuenta.PENDIENTE, settings.sesionMotivo)
    }

    fun cerrarSesion() = settings.cerrarSesion()

    /**
     * Guarda lo que el PC respondió sobre la cuenta (`ACCTST`). Si es la de la sesión abierta, la sesión se entera
     * sin volver a entrar. Una cuenta que no existe en el teléfono se ignora.
     */
    fun aplicarEstado(usuario: String, estado: String, rol: String?, motivo: String?) {
        if (estado !in EstadoCuenta.TODOS) return
        val cuenta = dao.porUsuario(normalizar(usuario)) ?: return
        val actualizada = cuenta.copy(estado = estado, rol = rol ?: cuenta.rol, motivo = motivo?.takeIf { it.isNotBlank() })
        dao.actualizar(actualizada)
        if (settings.sesionUsuario == actualizada.usuario) abrirSesion(actualizada)
    }

    /** Cuándo se creó la cuenta (para la pantalla de su estado). */
    fun registradoMs(usuario: String): Long? = dao.porUsuario(normalizar(usuario))?.creadoMs

    private fun abrirSesion(cuenta: UsuarioEntity) =
        settings.abrirSesion(cuenta.usuario, cuenta.nombre, cuenta.rol, cuenta.estado, cuenta.motivo)

    private fun validarClave(clave: String, confirmacion: String): AuthResult? = when {
        !Claves.esAceptable(clave) -> AuthResult.ClaveDebil
        clave != confirmacion -> AuthResult.ClavesDistintas
        else -> null
    }

    private fun bloqueo(cuenta: UsuarioEntity): AuthResult.Bloqueado? {
        val falta = cuenta.bloqueadoHastaMs - ahoraMs()
        return if (falta > 0) AuthResult.Bloqueado(ceil(falta / 1000.0).toInt()) else null
    }

    /** Cuenta un intento fallido; el que llega a [MAX_INTENTOS] bloquea la cuenta. */
    private fun fallo(cuenta: UsuarioEntity, resultado: AuthResult): AuthResult {
        val intentos = cuenta.intentosFallidos + 1
        if (intentos >= MAX_INTENTOS) {
            dao.actualizar(cuenta.copy(intentosFallidos = 0, bloqueadoHastaMs = ahoraMs() + BLOQUEO_MS))
            return AuthResult.Bloqueado((BLOQUEO_MS / 1000).toInt())
        }
        dao.actualizar(cuenta.copy(intentosFallidos = intentos))
        return resultado
    }

    companion object {
        const val MAX_INTENTOS = 5
        const val BLOQUEO_MS = 30_000L
        /** El nombre es el operador que viaja con cada lectura: mismo límite (D20). */
        const val MAX_NOMBRE = 60
        val USUARIO = Regex("[a-z0-9._-]{3,20}")
        val PREGUNTAS = listOf(
            "¿Cuál es el nombre de tu primera mascota?",
            "¿En qué ciudad naciste?",
            "¿Cuál es el segundo nombre de tu madre?",
            "¿Cómo se llamaba tu primera escuela?",
            "¿Cuál es tu comida favorita?",
        )

        fun normalizar(usuario: String): String = usuario.trim().lowercase()
        // La respuesta no distingue mayúsculas ni espacios de más: se escribe una vez y se recuerda meses después.
        fun normalizarRespuesta(respuesta: String): String = respuesta.trim().lowercase().replace(Regex("\\s+"), " ")
    }
}
