package com.sebasarchive.kardex.imagen

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import java.io.File
import kotlin.math.roundToInt

/**
 * Foto de perfil: se valida al elegirla y se recorta en un cuadrado antes de guardarla. El avatar se muestra
 * circular; el archivo queda cuadrado para que cualquier vista lo recorte igual.
 */
object RecorteFoto {
    /** Tamaño máximo del archivo elegido. El máximo de la foto de evidencia es otro (compresión a ~150 KB). */
    const val MAX_BYTES = 2 * 1024 * 1024
    /** Lado del cuadrado guardado: suficiente para el avatar en cualquier pantalla. */
    const val LADO = 512

    /** Lee la imagen reduciéndola si es enorme; devuelve null si el archivo no es una imagen válida. */
    fun cargar(archivo: File): Bitmap? {
        val limites = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(archivo.path, limites)
        if (limites.outWidth <= 0 || limites.outHeight <= 0) return null
        var muestra = 1
        while (maxOf(limites.outWidth, limites.outHeight) / (muestra * 2) >= 2048) muestra *= 2
        return BitmapFactory.decodeFile(archivo.path, BitmapFactory.Options().apply { inSampleSize = muestra })
    }

    /**
     * Recorta un cuadrado centrado (con el encuadre que eligió el usuario) y lo deja en [LADO] × [LADO].
     * [rotacion] en grados (múltiplos de 90), [zoom] ≥ 1, [panX]/[panY] en −1..1.
     */
    fun recortar(origen: Bitmap, rotacion: Int, zoom: Float, panX: Float, panY: Float, lado: Int = LADO): Bitmap {
        val giro = ((rotacion % 360) + 360) % 360
        val rotada = if (giro == 0) origen else {
            val matriz = Matrix().apply { postRotate(giro.toFloat()) }
            Bitmap.createBitmap(origen, 0, 0, origen.width, origen.height, matriz, true)
        }
        val ancho = rotada.width
        val alto = rotada.height
        val mayor = minOf(ancho, alto)
        val ladoOrigen = (mayor / zoom.coerceIn(1f, 4f)).roundToInt().coerceIn(1, mayor)
        val sobraX = (ancho - ladoOrigen).coerceAtLeast(0)
        val sobraY = (alto - ladoOrigen).coerceAtLeast(0)
        val centroX = ancho / 2f + panX.coerceIn(-1f, 1f) * sobraX / 2f
        val centroY = alto / 2f + panY.coerceIn(-1f, 1f) * sobraY / 2f
        val izquierda = (centroX - ladoOrigen / 2f).roundToInt().coerceIn(0, ancho - ladoOrigen)
        val arriba = (centroY - ladoOrigen / 2f).roundToInt().coerceIn(0, alto - ladoOrigen)
        val cuadrado = Bitmap.createBitmap(rotada, izquierda, arriba, ladoOrigen, ladoOrigen)
        if (cuadrado.width == lado) return cuadrado
        return Bitmap.createScaledBitmap(cuadrado, lado, lado, true)
    }
}
