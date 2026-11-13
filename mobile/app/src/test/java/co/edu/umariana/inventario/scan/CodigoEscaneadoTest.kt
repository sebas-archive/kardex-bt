package co.edu.umariana.inventario.scan

import org.junit.Assert.assertEquals
import org.junit.Test

/** El escáner lee códigos de barras y QR; de ambos sale el SKU del producto. */
class CodigoEscaneadoTest {
    @Test
    fun test_barcode_is_the_sku() {
        assertEquals("7701234000012", CodigoEscaneado.sku("7701234000012"))
        assertEquals("7701234000012", CodigoEscaneado.sku("  7701234000012\n"))
    }

    @Test
    fun test_qr_with_plain_sku() {
        assertEquals("A1-ROJO", CodigoEscaneado.sku("A1-ROJO"))
        assertEquals("7701234000012", CodigoEscaneado.sku("SKU:7701234000012"))
        assertEquals("7701234000012", CodigoEscaneado.sku("sku = 7701234000012"))
    }

    @Test
    fun test_qr_with_url() {
        assertEquals("7701234000012", CodigoEscaneado.sku("https://tienda.example/producto?ref=qr&sku=7701234000012&lote=4"))
        assertEquals("7701234000012", CodigoEscaneado.sku("https://tienda.example/p?SKU=7701234000012"))
        assertEquals("7701234000012", CodigoEscaneado.sku("https://tienda.example/productos/7701234000012"))  // sin parámetro: el último tramo
        assertEquals("7701234000012", CodigoEscaneado.sku("https://tienda.example/productos/7701234000012/"))
    }

    @Test
    fun test_qr_with_json() {
        assertEquals("7701234000012", CodigoEscaneado.sku("""{"nombre":"Café molido","sku":"7701234000012","precio":18500}"""))
        assertEquals("7701234000012", CodigoEscaneado.sku("""{ "SKU" : 7701234000012 }"""))
    }

    @Test
    fun test_unknown_content_is_kept_trimmed_and_cut_to_40_chars() {
        assertEquals("Lote 4 de café", CodigoEscaneado.sku(" Lote 4 de café "))
        assertEquals(40, CodigoEscaneado.sku("x".repeat(90)).length)
        assertEquals("", CodigoEscaneado.sku("   "))
    }
}
