package com.sebasarchive.kardex.sync

import com.sebasarchive.kardex.protocol.Message
import com.sebasarchive.kardex.protocol.Protocol
import com.sebasarchive.kardex.protocol.Rec
import java.io.BufferedOutputStream
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketTimeoutException
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Hace de PC para una conexión, con las mismas reglas que la sesión real (server/btsync/session.py):
 * READY + catálogo, COMMIT cada 25 con ACK acumulativo, un NAK por hueco e ignorar hasta el seq
 * esperado, y BYE tras END. Escucha en un socket TCP real de loopback.
 */
class FakePc(
    private val lastSeq: Long = 0,
    private val serverNowMs: Long = SERVER_NOW,
    private val nakOnce: Map<Long, String> = emptyMap(),  // seq -> motivo: la primera vez que llega "se corrompe"
    private val cutAfterRecs: Int? = null,                // corta la conexión al recibir el REC número N
    private val busy: Boolean = false,                    // ya hay otra sincronización: NAK|0|OCUPADO
    private val stallBeforeAck: Boolean = false,          // retiene los ACK hasta que el teléfono deja de enviar
    private val estadoCuenta: String = "ACTIVO",          // lo que responde ACCTST; sin ACTIVO rechaza todo REC
    private val motivoCuenta: String = "",
    private val fotoErr: Map<Long, String> = emptyMap(),     // seq -> motivo: responde FOTOERR en vez de FOTOOK
    private val cutOnFotoPart: Int? = null,                   // corta al recibir la parte N de cualquier foto
    private val nakFotoFinal: Long? = null,                   // la última parte de esa foto "llega corrupta": solo NAK
) {
    companion object {
        const val SERVER_NOW = 1_731_170_400_000L
        val CATALOGO = listOf(
            listOf("CATTAREA", "CATALOGO", "Catálogo", "", "", "ABIERTO", "2", "0"),
            listOf("CATITEM", "CATALOGO", "A1", "N"),
            listOf("CATITEM", "CATALOGO", "A2", "N"),
            listOf("CATPROD", "A1", "Producto A1", "Abarrotes", "UND"),
            listOf("CATPROD", "A2", "Café | molido", "Abarrotes", "UND"),
        )
    }

    val received = CopyOnWriteArrayList<Rec>()   // todo REC bien formado que llegó (incluye reenvíos)
    val accepted = CopyOnWriteArrayList<Rec>()   // lo que quedó "con COMMIT"
    val bursts = CopyOnWriteArrayList<Int>()     // con stallBeforeAck: cuántos REC llegaron en cada ráfaga
    val recibidos = CopyOnWriteArrayList<String>()  // tipo de cada mensaje que llegó después de ACCT, en orden
    val inicios = CopyOnWriteArrayList<String>()    // las tareas de cada INICIO
    val fotos = java.util.concurrent.ConcurrentHashMap<Long, ByteArray>()   // fotos completas aceptadas (FOTOOK)
    @Volatile var hello: Message? = null
    @Volatile var acct: Message? = null
    @Volatile private var error: Throwable? = null

    private val server = ServerSocket(0, 1, InetAddress.getLoopbackAddress())
    private val thread = Thread {
        try {
            server.use { serve(it.accept()) }
        } catch (t: Throwable) {
            error = t
        }
    }.apply { isDaemon = true; start() }

    fun connect(): BluetoothSocketLike {
        val socket = Socket(InetAddress.getLoopbackAddress(), server.localPort)
        return object : BluetoothSocketLike {
            override val inputStream: InputStream = socket.getInputStream()
            override val outputStream: OutputStream = socket.getOutputStream()
            override fun close() = socket.close()
        }
    }

    fun join() {
        thread.join(15_000)
        check(!thread.isAlive) { "FakePc no terminó" }
        error?.let { throw AssertionError("FakePc falló: $it", it) }
    }

    private fun drain(socket: Socket) {
        try {
            socket.soTimeout = 2000
            while (socket.getInputStream().read() >= 0) { /* hasta que el teléfono cierre */ }
        } catch (_: IOException) {
        }
    }

    private fun serve(socket: Socket) = socket.use { s ->
        val out = BufferedOutputStream(s.getOutputStream())
        fun send(vararg fields: String) = out.write(Protocol.frame(fields.toList()))

        if (busy) {  // como los transportes reales: avisa y cierra con cortesía
            send("NAK", "0", "OCUPADO")
            out.flush()
            s.shutdownOutput()
            drain(s)
            return
        }

        val reader = LineReader(s.getInputStream())
        val first = Protocol.parse(reader.readLine() ?: error("el teléfono cerró sin HELLO"))
        check(first.kind == "HELLO") { "se esperaba HELLO y llegó ${first.kind}" }
        hello = first
        val cuenta = Protocol.parse(reader.readLine() ?: error("el teléfono cerró sin ACCT"))
        check(cuenta.kind == "ACCT") { "se esperaba ACCT y llegó ${cuenta.kind}" }
        acct = cuenta
        val activa = estadoCuenta == "ACTIVO"
        send("ACCTST", Protocol.encodeText(cuenta.fields[0]), estadoCuenta, if (activa) "OPERADOR" else "",
            Protocol.encodeText(motivoCuenta))
        send("READY", lastSeq.toString(), serverNowMs.toString())
        for (linea in CATALOGO) send(linea[0], *linea.drop(1).map(Protocol::encodeText).toTypedArray())
        send("CAT_END")
        out.flush()

        var expected = lastSeq + 1
        var lastAcked = lastSeq
        var nakActive = false
        var rejected = 0
        var inserted = 0
        var recs = 0
        var burst = 0
        val uncommitted = ArrayList<Rec>()
        val pendingNaks = HashMap(nakOnce)
        val heldAcks = ArrayList<Long>()
        val partes = HashMap<Long, StringBuilder>()

        fun flushHeld() {
            for (ack in heldAcks) send("ACK", ack.toString())
            heldAcks.clear()
            out.flush()
        }

        fun commitAndAck() {
            accepted += uncommitted
            uncommitted.clear()
            val last = expected - 1
            if (last > lastAcked) {
                lastAcked = last
                if (stallBeforeAck) heldAcks += last else { send("ACK", last.toString()); out.flush() }
            }
        }

        fun reject(reason: String) {
            if (nakActive) return
            send("NAK", expected.toString(), reason)
            out.flush()
            rejected++
            nakActive = true
        }

        fun endBurst() {
            if (burst > 0) bursts += burst
            burst = 0
        }

        if (stallBeforeAck) s.soTimeout = 400
        while (true) {
            val line = try {
                reader.readLine()
            } catch (e: SocketTimeoutException) {  // el teléfono dejó de enviar: está esperando ACK
                endBurst()
                flushHeld()
                continue
            }
            if (line == null) return  // el teléfono cerró

            val msg = Protocol.parse(line)
            recibidos += msg.kind
            when (msg.kind) {
                "INICIO" -> inicios += msg.fields[0]
                "FOTO" -> {
                    val seq = msg.fields[0].toLong()
                    val parte = msg.fields[1].toInt()
                    val total = msg.fields[2].toInt()
                    if (cutOnFotoPart != null && parte >= cutOnFotoPart) return  // corte a mitad de la foto
                    if (parte == 1) {
                        if (uncommitted.isNotEmpty()) commitAndAck()  // como el PC real: confirma antes de la foto
                        partes[seq] = StringBuilder()
                    }
                    partes[seq]!!.append(msg.fields[4])
                    if (parte == total && nakFotoFinal == seq) {   // CRC de línea malo: el PC real solo manda NAK
                        partes.remove(seq)
                        send("NAK", expected.toString(), "CRC")
                        out.flush()
                    } else if (parte == total) {
                        val datos = java.util.Base64.getDecoder().decode(partes.remove(seq).toString())
                        val crc = java.util.zip.CRC32().apply { update(datos) }.value
                        val motivo = fotoErr[seq] ?: if ("%08X".format(crc) != msg.fields[3]) "CRC"
                            else if (seq > lastSeq && accepted.none { it.seq == seq }) "SIN_LECTURA" else null
                        if (motivo == null) { fotos[seq] = datos; send("FOTOOK", seq.toString()) }
                        else send("FOTOERR", seq.toString(), motivo)
                        out.flush()
                    }
                }
                "REC" -> {
                    val rec = Rec.fromMessage(msg)
                    received += rec
                    recs++
                    burst++
                    if (cutAfterRecs != null && recs >= cutAfterRecs) return  // corte: lo no confirmado se pierde
                    val corrupt = if (rec.seq == expected) pendingNaks.remove(rec.seq) else null
                    when {
                        !activa -> reject("CUENTA_NO_ACTIVA")
                        corrupt != null -> reject(corrupt)
                        rec.seq < expected -> Unit                 // duplicado
                        rec.seq > expected -> reject("SECUENCIA")  // hueco
                        else -> {
                            uncommitted += rec
                            expected++
                            inserted++
                            nakActive = false
                            if (uncommitted.size >= 25) commitAndAck()
                        }
                    }
                }
                "END" -> {
                    endBurst()
                    commitAndAck()
                    flushHeld()
                    send("BYE", inserted.toString(), rejected.toString())
                    out.flush()
                    s.shutdownOutput()
                    drain(s)
                    return
                }
                else -> error("mensaje inesperado del teléfono: ${msg.kind}")
            }
        }
    }
}
