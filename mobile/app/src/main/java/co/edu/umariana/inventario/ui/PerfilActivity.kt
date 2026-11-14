package co.edu.umariana.inventario.ui

import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import co.edu.umariana.inventario.imagen.RecorteFoto
import co.edu.umariana.inventario.ui.pantallas.PerfilScreen
import co.edu.umariana.inventario.ui.pantallas.PerfilUi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** Mi cuenta: foto, preferencias y cierre de sesión. La contraseña se recupera desde Acceso. */
class PerfilActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private var ui by mutableStateOf(PerfilUi())

    private val elegirFoto = registerForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) {
            lifecycleScope.launch {
                val archivo = withContext(Dispatchers.IO) { copiarConLimite(uri) }
                when {
                    archivo == null -> ui = ui.copy(error = Textos.t("La foto supera el máximo de 2 MB"))
                    !esImagen(archivo) -> ui = ui.copy(error = Textos.t("Elige una imagen JPEG, PNG o WebP"))
                    else -> abrir(FotoEditorActivity::class.java) {
                        putExtra(FotoEditorActivity.EXTRA_IMAGEN, archivo.path)
                    }
                }
            }
        }
    }

    private val editor = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { resultado ->
        val ruta = resultado.data?.getStringExtra(FotoEditorActivity.EXTRA_SALIDA)
        if (resultado.resultCode == RESULT_OK && ruta != null) guardarFoto(File(ruta))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val sesion = s.auth.sesion() ?: run { reemplazarPor(AuthActivity::class.java); return }
        ui = PerfilUi(
            foto = sesion.foto,
            correo = sesion.correo,
            tema = Apariencia.tema,
            idioma = Apariencia.idioma,
        )
        // La sesión ya trae foto y correo; si viene de una versión anterior, se completan desde Room sin bloquear.
        lifecycleScope.launch {
            val (foto, correo) = withContext(Dispatchers.IO) {
                s.auth.fotoDe(sesion.usuario) to s.auth.correoDe(sesion.usuario)
            }
            if (foto != ui.foto || correo != ui.correo) ui = ui.copy(foto = foto, correo = correo)
        }
        pantalla {
            PerfilScreen(
                sesion, ui,
                alPonerFoto = {
                    elegirFoto.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                },
                alEliminarFoto = { borrarFoto(sesion.usuario) },
                alCambiarTema = { valor ->
                    Apariencia.cambiarTema(s.settings, sesion.usuario, valor)
                    ui = ui.copy(tema = Apariencia.tema)
                },
                alCambiarIdioma = { valor ->
                    Apariencia.cambiarIdioma(s.settings, sesion.usuario, valor)
                    ui = ui.copy(idioma = Apariencia.idioma)
                },
                alCerrarSesion = {
                    s.auth.cerrarSesion()
                    reemplazarPor(AuthActivity::class.java)
                },
                alVolver = { finish() },
            )
        }
    }

    private fun abrir(destino: Class<*>, configurar: Intent.() -> Unit) {
        editor.launch(Intent(this, destino).apply(configurar))
    }

    /** Copia la imagen elegida a la caché sin pasar del límite (2 MB). */
    private fun copiarConLimite(uri: Uri): File? {
        val entrada = contentResolver.openInputStream(uri) ?: return null
        val destino = File(cacheDir, "foto-origen.jpg")
        destino.parentFile?.mkdirs()
        entrada.use { flujo ->
            destino.outputStream().use { salida ->
                val buffer = ByteArray(8 * 1024)
                var total = 0
                while (true) {
                    val leidos = flujo.read(buffer)
                    if (leidos <= 0) break
                    total += leidos
                    if (total > RecorteFoto.MAX_BYTES) return null
                    salida.write(buffer, 0, leidos)
                }
            }
        }
        return destino
    }

    private fun esImagen(archivo: File): Boolean {
        val limites = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(archivo.path, limites)
        return limites.outWidth > 0 && limites.outHeight > 0
    }

    private fun guardarFoto(recortada: File) {
        val sesion = s.auth.sesion() ?: return
        lifecycleScope.launch {
            val destino = withContext(Dispatchers.IO) {
                val carpeta = File(filesDir, "perfil").apply { mkdirs() }
                // Nombre único: si se edita la foto, la vista no reutiliza el mapa de bits anterior.
                val archivo = File(carpeta, "${sesion.usuario}-${System.currentTimeMillis()}.jpg")
                recortada.copyTo(archivo, overwrite = true)
                recortada.delete()
                val anterior = s.auth.fotoDe(sesion.usuario)
                if (anterior != null && anterior != archivo.path) File(anterior).delete()
                archivo
            }
            withContext(Dispatchers.IO) { s.auth.guardarFoto(sesion.usuario, destino.path) }
            ui = ui.copy(foto = destino.path, error = null)
        }
    }

    private fun borrarFoto(usuario: String) {
        lifecycleScope.launch {
            withContext(Dispatchers.IO) {
                s.auth.fotoDe(usuario)?.let { File(it).delete() }
                File(filesDir, "perfil/$usuario.jpg").delete()
            }
            withContext(Dispatchers.IO) { s.auth.guardarFoto(usuario, null) }
            ui = ui.copy(foto = null, error = null)
        }
    }
}
