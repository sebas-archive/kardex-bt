package co.edu.umariana.inventario.ui

import android.content.Intent
import android.graphics.Bitmap
import android.os.Bundle
import androidx.lifecycle.lifecycleScope
import co.edu.umariana.inventario.imagen.RecorteFoto
import co.edu.umariana.inventario.ui.pantallas.FotoEditorScreen
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** Editor de la foto de perfil: recibe una imagen y devuelve el cuadrado recortado. */
class FotoEditorActivity : PantallaActivity() {
    private lateinit var imagen: Bitmap

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val ruta = intent.getStringExtra(EXTRA_IMAGEN)
        val bitmap = ruta?.let { RecorteFoto.cargar(File(it)) }
        if (bitmap == null) {
            aviso("No se pudo leer la imagen")
            finish()
            return
        }
        imagen = bitmap
        pantalla {
            FotoEditorScreen(
                imagen,
                alGuardar = { rotacion, zoom, panX, panY -> guardar(rotacion, zoom, panX, panY) },
                alCancelar = { finish() },
            )
        }
    }

    private fun guardar(rotacion: Int, zoom: Float, panX: Float, panY: Float) {
        lifecycleScope.launch {
            val archivo = withContext(Dispatchers.IO) {
                runCatching {
                    val recortada = RecorteFoto.recortar(imagen, rotacion, zoom, panX, panY)
                    val destino = File(cacheDir, "fotos-perfil/recorte-${System.currentTimeMillis()}.jpg")
                    destino.parentFile?.mkdirs()
                    destino.outputStream().use { recortada.compress(Bitmap.CompressFormat.JPEG, 90, it) }
                    destino
                }.getOrNull()
            }
            if (archivo == null) {
                aviso("No se pudo leer la imagen")
                return@launch
            }
            setResult(RESULT_OK, Intent().putExtra(EXTRA_SALIDA, archivo.path))
            finish()
        }
    }

    companion object {
        const val EXTRA_IMAGEN = "imagen"
        const val EXTRA_SALIDA = "salida"
    }
}
