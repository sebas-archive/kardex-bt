package co.edu.umariana.inventario.sync

import co.edu.umariana.inventario.data.Catalog
import co.edu.umariana.inventario.data.CatalogRepository
import co.edu.umariana.inventario.data.ItemTareaEntity
import co.edu.umariana.inventario.data.TareaEntity
import co.edu.umariana.inventario.data.Outbox
import co.edu.umariana.inventario.data.ProductoEntity
import co.edu.umariana.inventario.protocol.EstadoCuentaPc
import co.edu.umariana.inventario.protocol.FrameError
import co.edu.umariana.inventario.protocol.Message
import co.edu.umariana.inventario.protocol.Protocol
import co.edu.umariana.inventario.protocol.Rec
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.FlowCollector
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import java.io.BufferedOutputStream
import java.io.Closeable
import java.io.EOFException
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream

/** Lo que el cliente necesita de un socket Bluetooth (permite probar sin radio). */
interface BluetoothSocketLike : Closeable {
    val inputStream: InputStream
    val outputStream: OutputStream
}

sealed class SyncProgress {
    /** El PC aceptó la conexión y dijo hasta qué `seq` tiene guardado. */
    data class Connected(val ultimoSeqServidor: Long, val porEnviar: Int) : SyncProgress()

    /** El PC confirmó (con COMMIT) todo hasta [confirmadoHasta]; [total] es el último `seq` de esta sesión. */
    data class Progress(val confirmadoHasta: Long, val total: Long) : SyncProgress()

    /** Sesión terminada con `BYE`. Si [pendientes] > 0 hay que volver a sincronizar. */
    data class Done(val aceptados: Int, val rechazados: Int, val pendientes: Int) : SyncProgress()

    /** El PC ya está sincronizando otro teléfono (`NAK|0|OCUPADO`). No se envió nada. */
    data object Busy : SyncProgress()

    /** El PC rechazó el saludo por otro motivo. */
    data class Rejected(val motivo: String) : SyncProgress()

    /** La conexión se cortó. Lo no confirmado queda en la bandeja de salida para el siguiente intento. */
    data class Cut(val motivo: String, val pendientes: Int) : SyncProgress()

    /**
     * La cuenta no está ACTIVO en el PC (pendiente, rechazada o suspendida): no se envió ninguna lectura.
     * Las [pendientes] siguen en el búfer y salen cuando el administrador active la cuenta.
     */
    data class CuentaNoActiva(val estado: String, val motivo: String?, val pendientes: Int) : SyncProgress()
}

/**
 * Sincroniza la bandeja de salida con el PC por una conexión ya abierta.
 *
 * - **Reanudación:** el `READY` del PC manda: hasta su `seq` todo está confirmado y se envía solo lo que sigue.
 * - **Reloj (D15):** `offset = hora del PC − reloj del teléfono ahora`; se envía `tsOriginalMs + offset`.
 *   La fila no se modifica y el desfase se recalcula en cada sesión: nunca se acumula.
 * - **Ventana:** como mucho [WINDOW] lecturas sin confirmar en vuelo.
 * - **Go-back-N:** ante `NAK|n|motivo` se reenvía desde `n`.
 * - **Cuenta:** tras `HELLO` va `ACCT` con el operador de la sesión; el PC responde su estado (`ACCTST`), que se
 *   entrega a [alEstado]. Si no es ACTIVO no se envía ninguna lectura: la sesión termina con `END|0`.
 *
 * Una llamada es un intento sobre un socket. Tras un [SyncProgress.Cut] (o un `Done` con pendientes)
 * quien llama abre otra conexión y vuelve a llamar: nada se duplica.
 */
class SyncClient(
    private val outbox: Outbox,
    private val catalog: CatalogRepository,
    private val deviceUuid: String,
    private val deviceName: String,
    private val cuentaUsuario: String,
    private val cuentaNombre: String,
    private val alEstado: (EstadoCuentaPc) -> Unit = {},
    private val nowMs: () -> Long = System::currentTimeMillis,
) {
    fun sync(socket: BluetoothSocketLike): Flow<SyncProgress> = flow {
        try {
            socket.use { session(it) }
        } catch (e: IOException) {
            emit(SyncProgress.Cut(e.message ?: e.javaClass.simpleName, outbox.contarPendientes()))
        } catch (e: FrameError) {
            emit(SyncProgress.Cut("respuesta inválida del PC (${e.reason})", outbox.contarPendientes()))
        } catch (e: NumberFormatException) {
            emit(SyncProgress.Cut("respuesta inválida del PC", outbox.contarPendientes()))
        }
    }.flowOn(Dispatchers.IO)

    private suspend fun FlowCollector<SyncProgress>.session(socket: BluetoothSocketLike) {
        val out = BufferedOutputStream(socket.outputStream)
        val reader = LineReader(socket.inputStream)
        fun read(): Message =
            Protocol.parse(reader.readLine() ?: throw EOFException("el PC cerró la conexión"))

        out.write(Protocol.frame(listOf("HELLO", Protocol.VERSION, Protocol.encodeText(deviceUuid), Protocol.encodeText(deviceName))))
        out.write(Protocol.frame(listOf("ACCT", Protocol.encodeText(cuentaUsuario), Protocol.encodeText(cuentaNombre))))
        out.flush()

        val cuentaMsg = read()
        if (cuentaMsg.kind == "NAK") {
            emit(if (cuentaMsg.fields[1] == "OCUPADO") SyncProgress.Busy else SyncProgress.Rejected(cuentaMsg.fields[1]))
            return
        }
        val cuenta = EstadoCuentaPc.fromMessage(cuentaMsg)
        alEstado(cuenta)
        val activa = cuenta.estado == "ACTIVO"

        val first = read()
        if (first.kind != "READY") throw FrameError("FORMAT", "se esperaba READY y llegó ${first.kind}")
        val last = first.fields[0].toLong()
        val offset = first.fields[1].toLong() - nowMs()  // D15: un desfase por sesión, nunca guardado
        outbox.reconciliar(last)

        val nuevo = readCatalog(::read)
        catalog.reemplazarTodo(nuevo)

        if (!activa) {  // sin cuenta activa no sale ninguna lectura: quedan en el búfer
            out.write(Protocol.frame(listOf("END", "0")))
            out.flush()
            while (read().kind != "BYE") { /* el PC cierra la sesión */ }
            emit(SyncProgress.CuentaNoActiva(cuenta.estado, cuenta.motivo, outbox.contarPendientes()))
            return
        }

        // Las tareas que el operador empezó y el PC aún ve como ASIGNADA: se avisa antes de las lecturas.
        val iniciadas = catalog.iniciadas()
        for (t in nuevo.tareas) {
            if (t.estado == "ASIGNADA" && t.id in iniciadas) out.write(Protocol.frame(listOf("INICIO", Protocol.encodeText(t.id))))
        }

        var total = outbox.ultimoSeq()
        emit(SyncProgress.Connected(last, maxOf(0L, total - last).toInt()))

        var confirmed = last
        var next = last + 1
        var endSent = false
        while (true) {
            while (!endSent && next <= total && next - 1 - confirmed < WINDOW) {
                val lectura = outbox.tomarParaEnviar(next)
                if (lectura == null) {  // no debería haber huecos; si lo hay, hasta aquí llega esta sesión
                    total = next - 1
                    break
                }
                out.write(
                    Rec(lectura.seq, lectura.tsOriginalMs + offset, lectura.idConteo, lectura.sku, lectura.cantidad,
                        lectura.operador, lectura.nota).toFrame()
                )
                next++
            }
            if (!endSent && next > total) {
                out.write(Protocol.frame(listOf("END", maxOf(0L, total - last).toString())))
                endSent = true
            }
            out.flush()

            val msg = read()
            when (msg.kind) {
                "ACK" -> {
                    confirmed = msg.fields[0].toLong()
                    outbox.confirmarHasta(confirmed)
                    emit(SyncProgress.Progress(confirmed, total))
                }
                // Go-back-N: el PC ignora todo hasta recibir el seq que espera. Si el END ya salió,
                // el PC cierra con lo que tenga y lo demás queda pendiente para la próxima sesión.
                "NAK" -> if (!endSent) next = msg.fields[0].toLong()
                "BYE" -> {
                    emit(SyncProgress.Done(msg.fields[0].toInt(), msg.fields[1].toInt(), outbox.contarPendientes()))
                    return
                }
            }
        }
    }

    private fun readCatalog(read: () -> Message): Catalog {
        val tareas = ArrayList<TareaEntity>()
        val items = ArrayList<ItemTareaEntity>()
        val productos = ArrayList<ProductoEntity>()
        while (true) {
            val m = read()
            val f = m.fields
            when (m.kind) {
                "CATTAREA" -> tareas += TareaEntity(f[0], f[1], f[2], f[3], f[4], f[5].toInt(), f[6].toInt())
                "CATITEM" -> items += ItemTareaEntity(f[0], f[1], f[2] == "S")
                "CATPROD" -> productos += ProductoEntity(f[0], f[1], f[2], f[3])
                "CAT_END" -> return Catalog(tareas, items, productos)
                else -> throw FrameError("FORMAT", "se esperaba el catálogo y llegó ${m.kind}")
            }
        }
    }

    companion object {
        /** Lecturas sin confirmar que se permiten en vuelo. */
        const val WINDOW = 50
    }
}
