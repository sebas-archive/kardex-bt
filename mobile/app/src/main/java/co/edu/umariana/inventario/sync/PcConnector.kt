package co.edu.umariana.inventario.sync

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothSocket
import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.util.UUID

/** El socket Bluetooth real, visto como [BluetoothSocketLike]. */
class AndroidBluetoothSocket(private val socket: BluetoothSocket) : BluetoothSocketLike {
    override val inputStream: InputStream get() = socket.inputStream
    override val outputStream: OutputStream get() = socket.outputStream
    override fun close() = socket.close()
}

/**
 * Abre la conexión RFCOMM hacia el PC. D22: socket **inseguro** —no exige emparejar ni pide código— hacia el
 * servicio con el UUID de la aplicación; Android lo busca por SDP, así que el PC no necesita estar emparejado.
 */
class PcConnector(context: Context) {
    private val contexto = context.applicationContext

    fun adaptador(): BluetoothAdapter? = contexto.getSystemService(BluetoothManager::class.java)?.adapter

    @SuppressLint("MissingPermission")  // la pantalla pide BLUETOOTH_CONNECT antes de llamar
    suspend fun conectar(direccion: String): BluetoothSocketLike = withContext(Dispatchers.IO) {
        val adaptador = adaptador() ?: throw IOException("Este teléfono no tiene Bluetooth")
        if (!adaptador.isEnabled) throw IOException("El Bluetooth está apagado")
        try {
            adaptador.cancelDiscovery()  // buscar y conectar a la vez hace fallar la conexión
            val socket = adaptador.getRemoteDevice(direccion).createInsecureRfcommSocketToServiceRecord(SERVICE_UUID)
            try {
                socket.connect()
            } catch (e: IOException) {
                runCatching { socket.close() }
                throw e
            }
            AndroidBluetoothSocket(socket)
        } catch (e: SecurityException) {
            throw IOException("Falta el permiso de Bluetooth", e)
        } catch (e: IllegalArgumentException) {
            throw IOException("Dirección Bluetooth inválida", e)
        }
    }

    companion object {
        /** UUID del servicio RFCOMM de la aplicación de escritorio (el mismo de `btsync.transports.bluez`). */
        val SERVICE_UUID: UUID = UUID.fromString("7a1c0b52-4f0e-4d6a-9c3b-5e2a6d9f1b01")
        /** Nombre Bluetooth con el que el PC se anuncia mientras la sincronización está abierta (D21). */
        const val NOMBRE_PC = "gestion_inventario"
    }
}
