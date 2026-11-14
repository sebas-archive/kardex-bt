package com.sebasarchive.kardex.auth

import android.util.Base64
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Mac
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec

/**
 * Contraseñas y respuestas de seguridad: nunca se guardan tal cual. Se deriva una clave con
 * **PBKDF2-HMAC-SHA256** y una sal aleatoria por usuario; se guarda `pbkdf2-sha256$<vueltas>$<sal>$<derivada>`.
 *
 * PBKDF2-HMAC-SHA256 se implementa con `Mac` porque el proveedor `PBKDF2WithHmacSHA256` solo existe desde
 * Android 8 (la app admite Android 6). La verificación sigue aceptando el prefijo antiguo `pbkdf2-sha1` para no
 * dejar fuera a una cuenta creada con una versión anterior; las claves nuevas se crean siempre con SHA-256.
 */
object Claves {
    /** Vueltas de PBKDF2: lo bastante lento para frenar un ataque por fuerza bruta, tolerable en un teléfono viejo. */
    const val ITERACIONES = 60_000
    private const val PREFIJO = "pbkdf2-sha256"
    private const val PREFIJO_LEGADO = "pbkdf2-sha1"
    private const val BITS = 256
    private const val HMAC = "HmacSHA256"
    private const val HASH = 32
    private val azar = SecureRandom()

    fun crear(secreto: String, iteraciones: Int = ITERACIONES): String {
        val sal = ByteArray(16).also(azar::nextBytes)
        return listOf(PREFIJO, iteraciones.toString(), b64(sal), b64(derivar(secreto, sal, iteraciones))).joinToString("$")
    }

    fun verificar(secreto: String, guardado: String): Boolean {
        val partes = guardado.split("$")
        if (partes.size != 4) return false
        val iteraciones = partes[1].toIntOrNull() ?: return false
        val sal = runCatching { Base64.decode(partes[2], Base64.NO_WRAP) }.getOrNull() ?: return false
        val esperado = runCatching { Base64.decode(partes[3], Base64.NO_WRAP) }.getOrNull() ?: return false
        val derivada = when (partes[0]) {
            PREFIJO -> derivar(secreto, sal, iteraciones)
            PREFIJO_LEGADO -> derivarSha1(secreto, sal, iteraciones)
            else -> return false
        }
        return MessageDigest.isEqual(esperado, derivada)  // comparación en tiempo constante
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

    /** PBKDF2-HMAC-SHA256 (RFC 2898) con `Mac`, disponible en todas las versiones que admite la app. */
    private fun derivar(secreto: String, sal: ByteArray, iteraciones: Int): ByteArray {
        val clave = secreto.toByteArray(Charsets.UTF_8)
        val bloques = (BITS + HASH * 8 - 1) / (HASH * 8)
        val salida = ByteArray(BITS / 8)
        val mac = Mac.getInstance(HMAC)
        var offset = 0
        for (bloque in 1..bloques) {
            mac.init(SecretKeySpec(clave, HMAC))
            mac.update(sal)
            mac.update(
                byteArrayOf(
                    (bloque ushr 24).toByte(), (bloque ushr 16).toByte(),
                    (bloque ushr 8).toByte(), bloque.toByte(),
                )
            )
            var u = mac.doFinal()
            val t = u.copyOf()
            repeat(iteraciones - 1) {
                mac.init(SecretKeySpec(clave, HMAC))
                u = mac.doFinal(u)
                for (i in t.indices) t[i] = (t[i].toInt() xor u[i].toInt()).toByte()
            }
            val copiar = minOf(t.size, salida.size - offset)
            System.arraycopy(t, 0, salida, offset, copiar)
            offset += copiar
        }
        clave.fill(0)
        return salida
    }

    /** Solo para verificar cuentas creadas antes del cambio a SHA-256. */
    private fun derivarSha1(secreto: String, sal: ByteArray, iteraciones: Int): ByteArray {
        val spec = PBEKeySpec(secreto.toCharArray(), sal, iteraciones, BITS)
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA1").generateSecret(spec).encoded
        } finally {
            spec.clearPassword()
        }
    }

    private fun b64(bytes: ByteArray) = Base64.encodeToString(bytes, Base64.NO_WRAP)
}
