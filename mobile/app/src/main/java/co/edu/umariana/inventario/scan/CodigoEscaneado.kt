package co.edu.umariana.inventario.scan

import java.net.URLDecoder

/**
 * Saca el SKU de lo que leyó el escáner. Un código de barras ya es el SKU (D14). Un QR de producto puede traer
 * el SKU solo, con prefijo (`SKU:…`), dentro de un JSON (`{"sku": "…"}`) o en una dirección web
 * (`…?sku=…` o como último tramo de la ruta).
 */
object CodigoEscaneado {
    const val MAX = 40
    private val EN_JSON = Regex("\"sku\"\\s*:\\s*\"?([^\",}\\s]+)", RegexOption.IGNORE_CASE)
    private val EN_PARAMETRO = Regex("[?&]sku=([^&#]+)", RegexOption.IGNORE_CASE)
    private val CON_PREFIJO = Regex("sku\\s*[:=]\\s*(.+)", RegexOption.IGNORE_CASE)

    fun sku(contenido: String): String {
        val texto = contenido.trim()
        if (texto.startsWith("{")) EN_JSON.find(texto)?.let { return limpiar(it.groupValues[1]) }
        if (texto.startsWith("http://", ignoreCase = true) || texto.startsWith("https://", ignoreCase = true)) {
            EN_PARAMETRO.find(texto)?.let { return limpiar(decodificar(it.groupValues[1])) }
            val ruta = texto.substringBefore('?').substringBefore('#').trimEnd('/')
            return limpiar(decodificar(ruta.substringAfterLast('/')))
        }
        CON_PREFIJO.matchEntire(texto)?.let { return limpiar(it.groupValues[1]) }
        return limpiar(texto)
    }

    private fun limpiar(valor: String) = valor.trim().take(MAX)
    private fun decodificar(valor: String) = runCatching { URLDecoder.decode(valor, "UTF-8") }.getOrDefault(valor)
}
