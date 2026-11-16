package co.edu.umariana.inventario.fotos

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.GraphicsMode
import java.io.ByteArrayOutputStream

@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class CompresorTest {
    @get:Rule val carpeta = TemporaryFolder()

    private fun png(ancho: Int, alto: Int): ByteArray {
        val bmp = Bitmap.createBitmap(ancho, alto, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.rgb(200, 120, 40)) }
        return ByteArrayOutputStream().also { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }.toByteArray()
    }

    @Test
    fun reduceElLadoMayorA1280YGuardaJpeg() {
        val destino = carpeta.newFile("foto.jpg")
        Compresor.comprimir(png(4000, 3000).inputStream(), destino)
        val opciones = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(destino.path, opciones)
        assertEquals(1280, opciones.outWidth)
        assertEquals(960, opciones.outHeight)
        assertEquals("image/jpeg", opciones.outMimeType)
    }

    @Test
    fun unaFotoPequenaNoSeAgranda() {
        val destino = carpeta.newFile("chica.jpg")
        Compresor.comprimir(png(640, 480).inputStream(), destino)
        val opciones = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(destino.path, opciones)
        assertEquals(640, opciones.outWidth)
        assertTrue(destino.length() in 1..2 * 1024 * 1024)
    }

    @Test(expected = IllegalArgumentException::class)
    fun loQueNoEsImagenSeRechaza() {
        Compresor.comprimir("no es una imagen".byteInputStream(), carpeta.newFile("x.jpg"))
    }
}
