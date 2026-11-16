package com.sebasarchive.kardex.ui

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.sebasarchive.kardex.DeviceIdentity
import com.sebasarchive.kardex.auth.AuthRepository
import com.sebasarchive.kardex.auth.CuentasDatabase
import com.sebasarchive.kardex.data.AppDatabase
import com.sebasarchive.kardex.data.CatalogRepository
import com.sebasarchive.kardex.data.FotoRepository
import com.sebasarchive.kardex.data.NotificacionRepository
import com.sebasarchive.kardex.data.PantallaAviso
import com.sebasarchive.kardex.data.TipoAviso
import com.sebasarchive.kardex.sync.PcConnector
import com.sebasarchive.kardex.sync.SyncClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flow
import com.sebasarchive.kardex.sync.SyncProgress
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import android.os.Build
import androidx.lifecycle.viewModelScope
import com.sebasarchive.kardex.sync.BluetoothSocketLike

/** Las piezas de la app, creadas una sola vez (sin framework de inyección: son pocas). */
class Servicios private constructor(val contexto: Context) {
    val db: AppDatabase = AppDatabase.abrir(contexto)
    val settings = SettingsStore(contexto)
    val catalogo = CatalogRepository(db.catalogo())
    val conector = PcConnector(contexto)
    val auth = AuthRepository(CuentasDatabase.abrir(contexto).usuarios(), settings)

    /** Compartido por todas las pantallas: el operador y el conteo son los mismos en todas. */
    val fotos = FotoRepository(db.fotos(), java.io.File(contexto.filesDir, "fotos"))
    val notificaciones = NotificacionRepository(db.notificaciones())
    val contar = CountViewModel(db.outbox(), catalogo, settings, fotos)

    /** El PC respondió en esta ejecución de la app: sin sesión, el acceso solo se ofrece después de conectar con él. */
    @Volatile var pcVerificado = false

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
                alEstado = { estadoPc ->
                    servicios.auth.aplicarEstado(sesion.usuario, estadoPc.estado, estadoPc.rol, estadoPc.motivo)
                    if (estadoPc.estado == "ACTIVO" && sesion.estado != "ACTIVO") {
                        servicios.notificaciones.crear(TipoAviso.CUENTA_ACTIVA, "", PantallaAviso.INICIO)
                    }
                },
                fotos = servicios.fotos)
            val runner = SyncRunner(
                conectar = { servicios.conector.conectar(direccion).also { socket = it } },
                sincronizar = cliente::sync,
            )
            runner.ejecutar().collect { estado ->
                _estado.value = estado
                avisar(estado)
            }
        }
    }

    /**
     * Solo comprueba que el PC responde (antes de iniciar sesión no hay operador que sincronizar): abre la conexión,
     * la cierra y termina en [SyncEstado.Listo]. Reutiliza los reintentos y los estados de la sincronización normal.
     */
    fun probar(direccion: String) {
        if (enCurso) return
        job = viewModelScope.launch {
            val runner = SyncRunner(
                conectar = { servicios.conector.conectar(direccion).also { socket = it } },
                sincronizar = { conexion -> flow { conexion.close(); emit(SyncProgress.Done(0, 0, 0)) } },
            )
            runner.ejecutar().collect { _estado.value = it }
        }
    }

    /** Deja un aviso local por los hitos de la sincronización (no llegan notificaciones en tiempo real). */
    private fun avisar(estado: SyncEstado) {
        viewModelScope.launch(Dispatchers.IO) {
            when (estado) {
                is SyncEstado.Listo -> {
                    if (estado.pendientes > 0) {
                        servicios.notificaciones.crear(TipoAviso.SYNC_CON_PENDIENTES, estado.pendientes.toString(), PantallaAviso.PENDIENTES)
                    } else {
                        servicios.notificaciones.crear(TipoAviso.SYNC_OK, estado.aceptados.toString(), PantallaAviso.PENDIENTES)
                    }
                }
                is SyncEstado.CuentaNoActiva -> {
                    val tipo = when (estado.estado) {
                        "PENDIENTE" -> TipoAviso.CUENTA_PENDIENTE
                        "SUSPENDIDO" -> TipoAviso.CUENTA_SUSPENDIDA
                        "RECHAZADO" -> TipoAviso.CUENTA_RECHAZADA
                        "ACTIVO" -> TipoAviso.CUENTA_ACTIVA
                        else -> TipoAviso.CUENTA_PENDIENTE
                    }
                    servicios.notificaciones.crear(tipo, estado.motivo.orEmpty(), PantallaAviso.ESTADO_CUENTA)
                }
                is SyncEstado.Cortado, is SyncEstado.PcNoDisponible -> {
                    servicios.notificaciones.crear(TipoAviso.SYNC_SIN_CONEXION, "", PantallaAviso.SINCRONIZAR)
                }
                else -> Unit
            }
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
