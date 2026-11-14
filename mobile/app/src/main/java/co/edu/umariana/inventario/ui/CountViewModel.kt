package co.edu.umariana.inventario.ui

import androidx.lifecycle.ViewModel
import co.edu.umariana.inventario.data.CatalogRepository
import co.edu.umariana.inventario.data.FotoRepository
import co.edu.umariana.inventario.data.LecturaEntity
import co.edu.umariana.inventario.data.Outbox
import co.edu.umariana.inventario.data.ProductoEntity
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.io.File

/** Resultado de [CountViewModel.guardar]: lo guardado o la primera regla que no se cumple. */
sealed class SaveResult {
    /** [reemplazo]: corrigió una lectura que aún no había salido (recuento). [skuDesconocido]: advertencia, se guardó igual. */
    data class Guardada(val seq: Long, val reemplazo: Boolean, val skuDesconocido: Boolean) : SaveResult()
    data object OperadorFaltante : SaveResult()
    data object SkuFaltante : SaveResult()
    data object CantidadInvalida : SaveResult()
    data object NotaLarga : SaveResult()
    data object DanadosInvalidos : SaveResult()
}

/**
 * Lógica de la pantalla «Contar». Guarda **siempre primero en la [Outbox]**: nada depende de que haya
 * conexión. Las funciones tocan Room: el que llama las corre fuera del hilo de la interfaz.
 *
 * El conteo es único y siempre está abierto, así que todas las lecturas llevan [CONTEO] como `id_conteo`.
 */
class CountViewModel(
    private val outbox: Outbox,
    private val catalogo: CatalogRepository,
    private val settings: SettingsStore,
    private val fotos: FotoRepository? = null,
    private val ahoraMs: () -> Long = System::currentTimeMillis,
) : ViewModel() {
    private val _operador = MutableStateFlow(settings.operador)
    val operador: StateFlow<String> = _operador.asStateFlow()

    /** Cambia y recuerda el operador. En blanco o de más de [MAX_OPERADOR] caracteres se ignora (la pantalla ya limita lo que se escribe). */
    fun setOperador(nombre: String) {
        val limpio = nombre.trim()
        if (limpio.isEmpty() || largo(limpio) > MAX_OPERADOR) return
        settings.operador = limpio
        _operador.value = limpio
    }

    /**
     * Guarda la lectura. [danados]: cuántas de las contadas están dañadas ("" = no se indicó; nunca más que la
     * cantidad). [foto]: un JPG ya comprimido que pasa a ser la evidencia de esta lectura (reemplaza la anterior).
     */
    fun guardar(sku: String, cantidad: String, nota: String, danados: String = "", foto: File? = null): SaveResult {
        val operador = _operador.value
        if (operador.isEmpty()) return SaveResult.OperadorFaltante
        val codigo = sku.trim()
        if (codigo.isEmpty()) return SaveResult.SkuFaltante
        if (!CANTIDAD.matches(cantidad)) return SaveResult.CantidadInvalida
        if (largo(nota) > MAX_NOTA) return SaveResult.NotaLarga
        if (danados.isNotEmpty() && (!CANTIDAD.matches(danados) || danados.toBigDecimal() > cantidad.toBigDecimal())) {
            return SaveResult.DanadosInvalidos
        }

        val ahora = ahoraMs()
        val desconocido = catalogo.producto(codigo) == null
        // Recontar: si la lectura de ese SKU aún no salió, se corrige en sitio; si ya salió, va una nueva
        // y el PC se queda con la más reciente (D13).
        if (outbox.reemplazar(CONTEO, codigo, cantidad, ahora, nota, danados)) {
            val seq = outbox.ultimaDe(CONTEO, codigo)!!.seq
            if (foto != null) fotos?.adjuntar(seq, foto)
            return SaveResult.Guardada(seq, reemplazo = true, skuDesconocido = desconocido)
        }
        val seq = outbox.insertar(
            LecturaEntity(tsOriginalMs = ahora, idConteo = CONTEO, sku = codigo,
                cantidad = cantidad, operador = operador, nota = nota, danados = danados)
        )
        if (foto != null) fotos?.adjuntar(seq, foto)
        return SaveResult.Guardada(seq, reemplazo = false, skuDesconocido = desconocido)
    }

    /** La lectura más reciente de ese SKU en el conteo actual, o null. */
    fun ultimaLectura(sku: String): LecturaEntity? = outbox.ultimaDe(CONTEO, sku.trim())

    /** Lo contado (una fila por SKU, la más reciente). */
    fun lecturas(): List<LecturaEntity> = outbox.vigentes(CONTEO)

    fun todasLasLecturas(): List<LecturaEntity> = outbox.todas()
    fun contarPendientes(): Int = outbox.contarPendientes()
    fun fotosPendientes(): Int = fotos?.contarPendientes() ?: 0
    fun conFoto(): Set<Long> = fotos?.conFoto() ?: emptySet()
    fun foto(seq: Long): File? = fotos?.archivo(seq)
    fun producto(sku: String): ProductoEntity? = catalogo.producto(sku.trim())
    fun productos(): List<ProductoEntity> = catalogo.productos()
    fun hayCatalogo(): Boolean = catalogo.productos().isNotEmpty()

    companion object {
        /** El único conteo: siempre abierto. Viaja como `id_conteo` en cada `REC`. */
        const val CONTEO = "ACTUAL"
        const val MAX_OPERADOR = 60
        const val MAX_NOTA = 255
        /** Cantidad con el formato del protocolo: decimal con punto, hasta 9 enteros y 3 decimales. */
        val CANTIDAD = Regex("\\d{1,9}(\\.\\d{1,3})?")

        // Los límites cuentan caracteres (como Oracle con CHAR), no unidades UTF-16: un emoji es uno.
        private fun largo(s: String) = s.codePointCount(0, s.length)
    }
}
