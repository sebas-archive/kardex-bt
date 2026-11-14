package com.sebasarchive.kardex.ui

import androidx.lifecycle.ViewModel
import com.sebasarchive.kardex.data.CatalogRepository
import com.sebasarchive.kardex.data.ItemTareaEntity
import com.sebasarchive.kardex.data.TareaEntity
import com.sebasarchive.kardex.data.LecturaEntity
import com.sebasarchive.kardex.data.Outbox
import com.sebasarchive.kardex.data.ProductoEntity
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Resultado de [CountViewModel.guardar]: lo guardado o la primera regla que no se cumple. */
sealed class SaveResult {
    /** [reemplazo]: corrigió una lectura que aún no había salido (recuento). [skuDesconocido]: advertencia, se guardó igual. */
    data class Guardada(val seq: Long, val reemplazo: Boolean, val skuDesconocido: Boolean) : SaveResult()
    data object OperadorFaltante : SaveResult()
    data object SinConteo : SaveResult()
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

    fun guardar(sku: String, cantidad: String, nota: String): SaveResult {
        val operador = _operador.value
        if (operador.isEmpty()) return SaveResult.OperadorFaltante
        val idConteo = _conteo.value ?: return SaveResult.SinConteo
        val codigo = sku.trim()
        if (codigo.isEmpty()) return SaveResult.SkuFaltante
        if (!CANTIDAD.matches(cantidad)) return SaveResult.CantidadInvalida
        if (largo(nota) > MAX_NOTA) return SaveResult.NotaLarga

        val ahora = ahoraMs()
        val desconocido = catalogo.producto(codigo) == null
        // Recontar: si la lectura de ese SKU aún no salió, se corrige en sitio; si ya salió, va una nueva
        // y el PC se queda con la más reciente (D13).
        if (outbox.reemplazar(idConteo, codigo, cantidad, ahora)) {
            val seq = outbox.ultimaDe(idConteo, codigo)!!.seq
            return SaveResult.Guardada(seq, reemplazo = true, skuDesconocido = desconocido)
        }
        val seq = outbox.insertar(
            LecturaEntity(tsOriginalMs = ahora, idConteo = idConteo, sku = codigo,
                cantidad = cantidad, operador = operador, nota = nota)
        )
        return SaveResult.Guardada(seq, reemplazo = false, skuDesconocido = desconocido)
    }

    /** La lectura más reciente de ese SKU en el conteo actual, o null. */
    fun ultimaLectura(sku: String): LecturaEntity? = _conteo.value?.let { outbox.ultimaDe(it, sku.trim()) }

    /** Lo contado en el conteo actual (una fila por SKU, la más reciente). */
    fun lecturas(): List<LecturaEntity> = _conteo.value?.let { outbox.vigentes(it) } ?: emptyList()

    fun todasLasLecturas(): List<LecturaEntity> = outbox.todas()
    fun contarPendientes(): Int = outbox.contarPendientes()
    fun tareas(): List<TareaEntity> = catalogo.tareas()
    fun items(idTarea: String): List<ItemTareaEntity> = catalogo.items(idTarea)
    fun iniciadas(): Set<String> = catalogo.iniciadas()

    /**
     * Si la tarea actual ya no llegó en el último catálogo (la cerraron o se la asignaron a otro operador), deja de
     * ser la actual: así no se cuentan lecturas en una tarea ajena. Devuelve su id para avisarlo, o null.
     */
    fun soltarTareaSiYaNoEsta(): String? {
        val actual = _conteo.value ?: return null
        if (catalogo.tareas().any { it.id == actual }) return null
        settings.conteo = null
        _conteo.value = null
        return actual
    }

    /** El operador empieza (o retoma) una tarea: se recuerda para avisar al PC y pasa a ser el conteo actual. */
    fun iniciarTarea(id: String) {
        catalogo.marcarIniciada(id)
        elegirConteo(id)
    }
    fun producto(sku: String): ProductoEntity? = catalogo.producto(sku.trim())
    fun hayCatalogo(): Boolean = catalogo.tareas().isNotEmpty()

    companion object {
        const val MAX_OPERADOR = 60
        const val MAX_NOTA = 255
        /** Cantidad con el formato del protocolo: decimal con punto, hasta 9 enteros y 3 decimales. */
        val CANTIDAD = Regex("\\d{1,9}(\\.\\d{1,3})?")

        // Los límites cuentan caracteres (como Oracle con CHAR), no unidades UTF-16: un emoji es uno.
        private fun largo(s: String) = s.codePointCount(0, s.length)
    }
}
