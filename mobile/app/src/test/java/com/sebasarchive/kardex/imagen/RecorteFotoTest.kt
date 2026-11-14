package com.sebasarchive.kardex.imagen

import android.graphics.Bitmap
import android.graphics.Color
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class RecorteFotoTest {
    private fun imagen(ancho: Int, alto: Int): Bitmap {
        val bitmap = Bitmap.createBitmap(ancho, alto, Bitmap.Config.ARGB_8888)
        for (x in 0 until ancho) for (y in 0 until alto) {
            bitmap.setPixel(x, y, if (x < ancho / 2) Color.RED else Color.BLUE)
        }
        return bitmap
    }

    @Test
    fun recortaCuadradoYEscalaAlTamanoDelAvatar() {
        val salida = RecorteFoto.recortar(imagen(240, 120), rotacion = 0, zoom = 1f, panX = 0f, panY = 0f)
        assertEquals(RecorteFoto.LADO, salida.width)
        assertEquals(RecorteFoto.LADO, salida.height)
    }

    @Test
    fun zoomYRotacionCambianElEncuadre() {
        val normal = RecorteFoto.recortar(imagen(300, 200), 0, 1f, 0f, 0f)
        val girada = RecorteFoto.recortar(imagen(300, 200), 90, 1f, 0f, 0f)
        val acercada = RecorteFoto.recortar(imagen(300, 200), 0, 2f, 0f, 0f)
        assertEquals(RecorteFoto.LADO, girada.width)
        assertEquals(RecorteFoto.LADO, acercada.width)
        assertNotEquals(normal.getPixel(10, 10), girada.getPixel(10, 10))
    }
}
