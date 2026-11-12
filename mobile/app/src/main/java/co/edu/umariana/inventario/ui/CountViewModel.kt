package co.edu.umariana.inventario.ui

import androidx.lifecycle.ViewModel
import co.edu.umariana.inventario.data.CatalogRepository
import co.edu.umariana.inventario.data.ConteoEntity
import co.edu.umariana.inventario.data.LecturaEntity
import co.edu.umariana.inventario.data.Outbox
import co.edu.umariana.inventario.data.ProductoEntity
import co.edu.umariana.inventario.data.UbicacionEntity
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Resultado de [CountViewModel.guardar]: lo guardado o la primera regla que no se cumple. */
sealed class SaveResult {
    /** [reemplazo]: corrigió una lectura que aún no había salido (recuento). [skuDesconocido]: advertencia, se guardó igual. */
    data class Guardada(val seq: Long, val reemplazo: Boolean, val skuDesconocido: Boolean) : SaveResult()
    data object OperadorFaltante : SaveResult()
    data object SinConteo : SaveResult()
    data object UbicacionFaltante : SaveResult()
    data object SkuFaltante : SaveResult()
    data object CantidadInvalida : SaveResult()
    data object NotaLarga : SaveResult()
}

/**
 * Lógica de la pantalla «Contar». Guarda **siempre primero en la [Outbox]**: nada depende de que haya
 * conexión. Las funciones tocan Room: el que llama las corre fuera del hilo de la interfaz.
 */
class CountViewModel(
    private val outbox: Outbox,
    private val catalogo: CatalogRepository,
    private val settings: SettingsStore,
    private val ahoraMs: () -> Long = System::currentTimeMillis,
) : ViewModel() {
    private val _operador = MutableStateFlow(settings.operador)
    val operador: StateFlow<String> = _operador.asStateFlow()
    private val _conteo = MutableStateFlow(settings.conteo)
    val conteo: StateFlow<String?> = _conteo.asStateFlow()
    private val _ubicacion = MutableStateFlow(settings.ubicacion)
    val ubicacion: StateFlow<String?> = _ubicacion.asStateFlow()

    /** Cambia y recuerda el operador. En blanco o de más de [MAX_OPERADOR] caracteres se ignora (la pantalla ya limita lo que se escribe). */
    fun setOperador(nombre: String) {
        val limpio = nombre.trim()
        if (limpio.isEmpty() || largo(limpio) > MAX_OPERADOR) return
        settings.operador = limpio
        _operador.value = limpio
    }

    fun elegirConteo(id: String) {
        settings.conteo = id
        _conteo.value = id
    }

    fun elegirUbicacion(cod: String) {
        settings.ubicacion = cod
        _ubicacion.value = cod
    }

    fun guardar(ubicacion: String, sku: String, cantidad: String, nota: String): SaveResult {
        val operador = _operador.value
        if (operador.isEmpty()) return SaveResult.OperadorFaltante
        val idConteo = _conteo.value ?: return SaveResult.SinConteo
        val ubic = ubicacion.trim()
        val codigo = sku.trim()
        if (ubic.isEmpty()) return SaveResult.UbicacionFaltante
        if (codigo.isEmpty()) return SaveResult.SkuFaltante
        if (!CANTIDAD.matches(cantidad)) return SaveResult.CantidadInvalida
        if (largo(nota) > MAX_NOTA) return SaveResult.NotaLarga

        val ahora = ahoraMs()
        val desconocido = catalogo.producto(codigo) == null
        // Recontar: si la lectura de esa ubicación y SKU aún no salió, se corrige en sitio; si ya salió, va una nueva
        // y el PC se queda con la más reciente (D13).
        if (outbox.reemplazar(idConteo, ubic, codigo, cantidad, ahora)) {
            val seq = outbox.ultimaDe(idConteo, ubic, codigo)!!.seq
            return SaveResult.Guardada(seq, reemplazo = true, skuDesconocido = desconocido)
        }
        val seq = outbox.insertar(
            LecturaEntity(tsOriginalMs = ahora, idConteo = idConteo, ubicacion = ubic, sku = codigo,
                cantidad = cantidad, operador = operador, nota = nota)
        )
        return SaveResult.Guardada(seq, reemplazo = false, skuDesconocido = desconocido)
    }

    /** La lectura más reciente de esa ubicación y SKU en el conteo actual, o null. */
    fun ultimaLectura(ubicacion: String, sku: String): LecturaEntity? =
        _conteo.value?.let { outbox.ultimaDe(it, ubicacion.trim(), sku.trim()) }

    /** Lo contado en una ubicación del conteo actual (una fila por SKU, la más reciente). */
    fun lecturasDe(ubicacion: String): List<LecturaEntity> =
        _conteo.value?.let { outbox.vigentesEn(it, ubicacion) } ?: emptyList()

    fun todasLasLecturas(): List<LecturaEntity> = outbox.todas()
    fun contarPendientes(): Int = outbox.contarPendientes()
    fun conteos(): List<ConteoEntity> = catalogo.conteos()
    fun ubicaciones(): List<UbicacionEntity> = catalogo.ubicaciones()
    fun producto(sku: String): ProductoEntity? = catalogo.producto(sku.trim())
    fun hayCatalogo(): Boolean = catalogo.conteos().isNotEmpty()

    companion object {
        const val MAX_OPERADOR = 60
        const val MAX_NOTA = 255
        /** Cantidad con el formato del protocolo: decimal con punto, hasta 9 enteros y 3 decimales. */
        val CANTIDAD = Regex("\\d{1,9}(\\.\\d{1,3})?")

        // Los límites cuentan caracteres (como Oracle con CHAR), no unidades UTF-16: un emoji es uno.
        private fun largo(s: String) = s.codePointCount(0, s.length)
    }
}
