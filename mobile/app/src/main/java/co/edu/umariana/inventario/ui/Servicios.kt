package co.edu.umariana.inventario.ui

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import co.edu.umariana.inventario.DeviceIdentity
import co.edu.umariana.inventario.auth.AuthRepository
import co.edu.umariana.inventario.auth.CuentasDatabase
import co.edu.umariana.inventario.data.AppDatabase
import co.edu.umariana.inventario.data.CatalogRepository
import co.edu.umariana.inventario.sync.PcConnector
import co.edu.umariana.inventario.sync.SyncClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import android.os.Build
import androidx.lifecycle.viewModelScope
import co.edu.umariana.inventario.sync.BluetoothSocketLike

/** Las piezas de la app, creadas una sola vez (sin framework de inyección: son pocas). */
class Servicios private constructor(val contexto: Context) {
    val db: AppDatabase = AppDatabase.abrir(contexto)
    val settings = SettingsStore(contexto)
    val catalogo = CatalogRepository(db.catalogo())
    val conector = PcConnector(contexto)
    val auth = AuthRepository(CuentasDatabase.abrir(contexto).usuarios(), settings)

    /** Compartido por todas las pantallas: el operador y el conteo son los mismos en todas. */
    val contar = CountViewModel(db.outbox(), catalogo, settings)

    companion object {
        @Volatile private var instancia: Servicios? = null
        fun de(context: Context): Servicios = instancia ?: synchronized(this) {
            instancia ?: Servicios(context.applicationContext).also { instancia = it }
        }
    }
}

/** Sincronización con el PC: sobrevive a girar la pantalla y se cancela al salir. */
class SyncViewModel(private val servicios: Servicios) : ViewModel() {
    private val _estado = MutableStateFlow<SyncEstado?>(null)
    val estado: StateFlow<SyncEstado?> = _estado.asStateFlow()
    private var job: Job? = null
    @Volatile private var socket: BluetoothSocketLike? = null

    val enCurso: Boolean get() = job?.isActive == true

    fun iniciar(direccion: String) {
        if (enCurso) return
        job = viewModelScope.launch {
            val uuid = withContext(Dispatchers.IO) { DeviceIdentity.get(servicios.contexto) }
            val sesion = servicios.auth.sesion() ?: return@launch
            // El PC responde el estado de la cuenta (ACCTST): se guarda para que la app sepa si puede trabajar.
            val cliente = SyncClient(servicios.db.outbox(), servicios.catalogo, uuid, Build.MODEL ?: "Android",
                sesion.usuario, sesion.nombre,
                alEstado = { servicios.auth.aplicarEstado(sesion.usuario, it.estado, it.rol, it.motivo) })
            val runner = SyncRunner(
                conectar = { servicios.conector.conectar(direccion).also { socket = it } },
                sincronizar = cliente::sync,
            )
            runner.ejecutar().collect { _estado.value = it }
        }
    }

    /** Corta la conexión abierta (cerrar el socket es lo que desbloquea una lectura pendiente). */
    fun cancelar() {
        job?.cancel()
        runCatching { socket?.close() }
        socket = null
        _estado.value = null
    }

    override fun onCleared() = cancelar()
}

class SyncViewModelFactory(private val servicios: Servicios) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T = SyncViewModel(servicios) as T
}
