package co.edu.umariana.inventario.auth

import android.util.Base64
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

/**
 * Contraseñas y respuestas de seguridad: nunca se guardan tal cual. Se deriva una clave con PBKDF2 y una sal
 * aleatoria por usuario, y se guarda `pbkdf2-sha1$<vueltas>$<sal>$<derivada>`.
 *
 * PBKDF2 con HMAC-SHA1 porque es el que existe en todos los Android que admite la app (el de SHA-256 llegó en Android 8).
 */
object Claves {
    /** Vueltas de PBKDF2: lo bastante lento para frenar un ataque por fuerza bruta, tolerable en un teléfono viejo. */
    const val ITERACIONES = 60_000
    private const val PREFIJO = "pbkdf2-sha1"
    private const val BITS = 256
    private val azar = SecureRandom()

    fun crear(secreto: String, iteraciones: Int = ITERACIONES): String {
        val sal = ByteArray(16).also(azar::nextBytes)
        return listOf(PREFIJO, iteraciones.toString(), b64(sal), b64(derivar(secreto, sal, iteraciones))).joinToString("$")
    }

    fun verificar(secreto: String, guardado: String): Boolean {
        val partes = guardado.split("$")
        if (partes.size != 4 || partes[0] != PREFIJO) return false
        val iteraciones = partes[1].toIntOrNull() ?: return false
        val sal = runCatching { Base64.decode(partes[2], Base64.NO_WRAP) }.getOrNull() ?: return false
        val esperado = runCatching { Base64.decode(partes[3], Base64.NO_WRAP) }.getOrNull() ?: return false
        return MessageDigest.isEqual(esperado, derivar(secreto, sal, iteraciones))  // comparación en tiempo constante
    }

    /** Qué tan fuerte es una contraseña, de 0 (vacía) a 4: largo y variedad de caracteres. */
    fun fuerza(clave: String): Int {
        if (clave.isEmpty()) return 0
        var puntos = 0
        if (clave.length >= 8) puntos++
        if (clave.length >= 12) puntos++
        if (clave.any { it.isLowerCase() } && clave.any { it.isUpperCase() }) puntos++
        if (clave.any { it.isDigit() } && clave.any { it.isLetter() }) puntos++
        if (clave.any { !it.isLetterOrDigit() }) puntos++
        return puntos.coerceAtMost(4)
    }

    /** La regla mínima: 8 caracteres o más, con al menos una letra y un número. */
    fun esAceptable(clave: String): Boolean = clave.length >= 8 && clave.any { it.isLetter() } && clave.any { it.isDigit() }

    private fun derivar(secreto: String, sal: ByteArray, iteraciones: Int): ByteArray {
        val spec = PBEKeySpec(secreto.toCharArray(), sal, iteraciones, BITS)
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA1").generateSecret(spec).encoded
        } finally {
            spec.clearPassword()
        }
    }

    private fun b64(bytes: ByteArray) = Base64.encodeToString(bytes, Base64.NO_WRAP)
}
