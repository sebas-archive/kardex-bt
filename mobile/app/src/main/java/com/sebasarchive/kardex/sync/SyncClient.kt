package com.sebasarchive.kardex.sync

import com.sebasarchive.kardex.data.Catalog
import com.sebasarchive.kardex.data.CatalogRepository
import com.sebasarchive.kardex.data.ConteoEntity
import com.sebasarchive.kardex.data.Outbox
import com.sebasarchive.kardex.data.ProductoEntity
import com.sebasarchive.kardex.data.UbicacionEntity
import com.sebasarchive.kardex.protocol.FrameError
import com.sebasarchive.kardex.protocol.Message
import com.sebasarchive.kardex.protocol.Protocol
import com.sebasarchive.kardex.protocol.Rec
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
}

/**
 * Sincroniza la bandeja de salida con el PC por una conexión ya abierta.
 *
 * - **Reanudación:** el `READY` del PC manda: hasta su `seq` todo está confirmado y se envía solo lo que sigue.
 * - **Reloj (D15):** `offset = hora del PC − reloj del teléfono ahora`; se envía `tsOriginalMs + offset`.
 *   La fila no se modifica y el desfase se recalcula en cada sesión: nunca se acumula.
 * - **Ventana:** como mucho [WINDOW] lecturas sin confirmar en vuelo.
 * - **Go-back-N:** ante `NAK|n|motivo` se reenvía desde `n`.
 *
 * Una llamada es un intento sobre un socket. Tras un [SyncProgress.Cut] (o un `Done` con pendientes)
 * quien llama abre otra conexión y vuelve a llamar: nada se duplica.
 */
class SyncClient(
    private val outbox: Outbox,
    private val catalog: CatalogRepository,
    private val deviceUuid: String,
    private val deviceName: String,
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

        out.write(Protocol.frame(listOf("HELLO", "1", Protocol.encodeText(deviceUuid), Protocol.encodeText(deviceName))))
        out.flush()

        val first = read()
        if (first.kind == "NAK") {
            emit(if (first.fields[1] == "OCUPADO") SyncProgress.Busy else SyncProgress.Rejected(first.fields[1]))
            return
        }
        if (first.kind != "READY") throw FrameError("FORMAT", "se esperaba READY y llegó ${first.kind}")
        val last = first.fields[0].toLong()
        val offset = first.fields[1].toLong() - nowMs()  // D15: un desfase por sesión, nunca guardado
        outbox.reconciliar(last)

        catalog.reemplazarTodo(readCatalog(::read))

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
                    Rec(lectura.seq, lectura.tsOriginalMs + offset, lectura.idConteo, lectura.ubicacion,
                        lectura.sku, lectura.cantidad, lectura.operador, lectura.nota).toFrame()
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
        val conteos = ArrayList<ConteoEntity>()
        val ubicaciones = ArrayList<UbicacionEntity>()
        val productos = ArrayList<ProductoEntity>()
        while (true) {
            val m = read()
            when (m.kind) {
                "CATCONTEO" -> conteos += ConteoEntity(m.fields[0], m.fields[1])
                "CATUBIC" -> ubicaciones += UbicacionEntity(m.fields[0], m.fields[1], m.fields[2])
                "CATPROD" -> productos += ProductoEntity(m.fields[0], m.fields[1], m.fields[2], m.fields[3])
                "CAT_END" -> return Catalog(conteos, ubicaciones, productos)
                else -> throw FrameError("FORMAT", "se esperaba el catálogo y llegó ${m.kind}")
            }
        }
    }

    companion object {
        /** Lecturas sin confirmar que se permiten en vuelo. */
        const val WINDOW = 50
    }
}
