package co.edu.umariana.inventario.auth

import android.util.Base64
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** PBKDF2-HMAC-SHA256 contra un vector conocido, y compatibilidad con el prefijo antiguo. */
@RunWith(RobolectricTestRunner::class)
class ClavesTest {
    private fun hex(texto: String): ByteArray = texto.chunked(2).map { it.toInt(16).toByte() }.toByteArray()

    @Test
    fun pbkdf2HmacSha256CoincideConElVectorConocido() {
        // RFC 7914 / vector habitual: PBKDF2-HMAC-SHA256("password", "salt", 1, 32).
        val esperado = hex("120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b")
        val guardado = "pbkdf2-sha256$1$" +
            Base64.encodeToString("salt".toByteArray(), Base64.NO_WRAP) + "$" +
            Base64.encodeToString(esperado, Base64.NO_WRAP)
        assertTrue(Claves.verificar("password", guardado))
        assertFalse(Claves.verificar("Password", guardado))
    }

    @Test
    fun crearUsaSha256YSalPorUsuario() {
        val primera = Claves.crear("conteo2026", iteraciones = 1_000)
        val segunda = Claves.crear("conteo2026", iteraciones = 1_000)
        assertTrue(primera.startsWith("pbkdf2-sha256$1000$"))
        assertTrue(segunda.startsWith("pbkdf2-sha256$1000$"))
        assertFalse(primera == segunda) // misma clave, sal distinta
        assertTrue(Claves.verificar("conteo2026", primera))
        assertFalse(Claves.verificar("conteo2027", primera))
    }

    @Test
    fun verificarAceptaUnaCuentaViejaConSha1() {
        val sal = "sal-vieja".toByteArray()
        val spec = javax.crypto.spec.PBEKeySpec("conteo2026".toCharArray(), sal, 1_000, 256)
        val derivada = javax.crypto.SecretKeyFactory.getInstance("PBKDF2WithHmacSHA1").generateSecret(spec).encoded
        val guardado = "pbkdf2-sha1$1000$" +
            Base64.encodeToString(sal, Base64.NO_WRAP) + "$" +
            Base64.encodeToString(derivada, Base64.NO_WRAP)
        assertTrue(Claves.verificar("conteo2026", guardado))
    }
}
