package com.sebasarchive.kardex.fotos

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import java.io.File
import java.io.InputStream

/** Reduce una foto antes de guardarla: JPEG, el lado mayor como mucho [MAX_LADO] px, calidad [CALIDAD] (~150 KB). */
object Compresor {
    const val MAX_LADO = 1280
    const val CALIDAD = 70

    /** Lee la imagen de [entrada] y la deja en [destino]. Lanza IllegalArgumentException si no es una imagen. */
    fun comprimir(entrada: InputStream, destino: File, maxLado: Int = MAX_LADO, calidad: Int = CALIDAD) {
        val bytes = entrada.use { it.readBytes() }
        val limites = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, limites)
        require(limites.outWidth > 0 && limites.outHeight > 0) { "No es una imagen" }
        // Primero se decodifica reducida en potencias de 2 (no carga 12 MP en memoria) y luego se ajusta exacto.
        var muestra = 1
        while (maxOf(limites.outWidth, limites.outHeight) / (muestra * 2) >= maxLado) muestra *= 2
        val decodificada = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = muestra })
            ?: throw IllegalArgumentException("No es una imagen")
        val mayor = maxOf(decodificada.width, decodificada.height)
        val final = if (mayor <= maxLado) decodificada else Bitmap.createScaledBitmap(
            decodificada, decodificada.width * maxLado / mayor, decodificada.height * maxLado / mayor, true)
        destino.parentFile?.mkdirs()
        destino.outputStream().use { final.compress(Bitmap.CompressFormat.JPEG, calidad, it) }
    }
}
