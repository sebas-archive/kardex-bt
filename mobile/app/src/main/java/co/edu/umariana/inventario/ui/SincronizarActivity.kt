package co.edu.umariana.inventario.ui

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import co.edu.umariana.inventario.sync.PcConnector
import co.edu.umariana.inventario.ui.pantallas.SincronizarScreen
import co.edu.umariana.inventario.ui.pantallas.SincronizarUi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Sincronizar (D22): si ya se eligió el PC, conecta de inmediato —sin buscar, sin emparejar, sin códigos—. La primera
 * vez busca «gestion_inventario» y se elige. Reintenta solo si se corta; avisa si el PC está ocupado o no responde.
 */
@SuppressLint("MissingPermission")  // los permisos se piden en `asegurarBluetooth` antes de tocar el adaptador
class SincronizarActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private val vm: SyncViewModel by viewModels { SyncViewModelFactory(Servicios.de(this)) }
    private var ui by mutableStateOf(SincronizarUi())
    /** Modo «conectar primero»: la app se abrió sin sesión; se comprueba el PC y se sigue al acceso. */
    private val soloConectar by lazy { intent.getBooleanExtra(EXTRA_SOLO_CONECTAR, false) }
    private var pendiente: (() -> Unit)? = null
    private var receptorActivo = false
    private var seqInicial: Long? = null  // primer seq de esta sincronización: el progreso se mide desde ahí

    private val pedirPermisos = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { resultado ->
        if (resultado.values.all { it }) pendiente?.invoke()
        else mostrar(Textos.t("Sin permiso de Bluetooth. Actívalo en Ajustes > Aplicaciones > Inventario > Permisos."))
    }
    private val pedirEncender = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        if (s.conector.adaptador()?.isEnabled == true) pendiente?.invoke() else mostrar(Textos.t("El Bluetooth sigue apagado."))
    }

    private val receptor = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                BluetoothDevice.ACTION_FOUND, BluetoothDevice.ACTION_NAME_CHANGED -> {
                    val dispositivo = if (Build.VERSION.SDK_INT >= 33)
                        intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice::class.java)
                    else @Suppress("DEPRECATION") intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE)
                    if (dispositivo != null) agregarPc(dispositivo.address, dispositivo.name ?: intent.getStringExtra(BluetoothDevice.EXTRA_NAME))
                }
                BluetoothAdapter.ACTION_DISCOVERY_FINISHED -> {
                    ui = ui.copy(buscando = false)
                    if (ui.encontrados.isEmpty()) mostrar(
                        Textos.t("No encontré «{pc}». En el PC pulsa «Iniciar sincronización» y acércate. En Android 10 o anterior la ubicación del teléfono debe estar encendida para buscar.",
                            "pc" to PcConnector.NOMBRE_PC))
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        ui = ui.copy(pcNombre = s.settings.pcNombre, pcDireccion = s.settings.pcDireccion, puedeCambiarPc = puedeCambiarPc(), soloConectar = soloConectar)
        pantalla {
            SincronizarScreen(
                ui,
                alSincronizar = ::sincronizar,
                alBuscar = ::buscar,
                alElegirPc = { direccion, nombre ->
                    s.settings.pcDireccion = direccion
                    s.settings.pcNombre = nombre
                    detenerBusqueda()
                    ui = ui.copy(pcNombre = nombre, pcDireccion = direccion, encontrados = emptyList(), mensaje = null, puedeCambiarPc = puedeCambiarPc())
                    sincronizar()
                },
                alVolver = { finish() },
            )
        }
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) { vm.estado.collect(::alCambiarEstado) }
        }
        contarPendientes()
    }

    override fun onStart() {
        super.onStart()
        // Con el PC ya elegido se conecta de inmediato; la primera vez hay que buscarlo.
        if (!vm.enCurso && vm.estado.value == null) {
            if (s.settings.pcDireccion != null) sincronizar() else buscar()
        }
    }

    override fun onStop() {
        super.onStop()
        detenerBusqueda()
    }

    private fun alCambiarEstado(estado: SyncEstado?) {
        when (estado) {
            is SyncEstado.Sincronizando -> {
                val inicio = seqInicial ?: estado.confirmadoHasta.also { seqInicial = it }
                ui = ui.copy(estado = estado, enviadas = estado.confirmadoHasta - inicio, porEnviar = estado.total - inicio)
            }
            null, is SyncEstado.Conectando -> {
                seqInicial = null
                ui = ui.copy(estado = estado, enviadas = 0, porEnviar = 0)
            }
            else -> {
                ui = ui.copy(estado = estado)
                contarPendientes()
                if (soloConectar && estado is SyncEstado.Listo) {  // PC conectado: se ve el visto un instante y sigue el acceso
                    s.pcVerificado = true
                    lifecycleScope.launch {
                        delay(900)
                        reemplazarPor(AuthActivity::class.java)
                    }
                }
            }
        }
    }

    private fun contarPendientes() {
        lifecycleScope.launch { ui = ui.copy(pendientes = withContext(Dispatchers.IO) { s.contar.contarPendientes() }) }
    }

    private fun mostrar(mensaje: String?) {
        ui = ui.copy(mensaje = mensaje)
    }

    // ------------------------------------------------------------------ permisos y Bluetooth encendido
    private fun asegurarBluetooth(buscando: Boolean, accion: () -> Unit) {
        val adaptador = s.conector.adaptador() ?: return mostrar(Textos.t("Este teléfono no tiene Bluetooth."))
        val necesarios = buildList {
            if (Build.VERSION.SDK_INT >= 31) {
                add(Manifest.permission.BLUETOOTH_CONNECT)
                if (buscando) add(Manifest.permission.BLUETOOTH_SCAN)
            } else if (buscando) add(Manifest.permission.ACCESS_FINE_LOCATION)  // Android ≤ 11: buscar exige ubicación
        }
        val faltan = necesarios.filter { ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED }
        if (faltan.isNotEmpty()) {
            pendiente = { asegurarBluetooth(buscando, accion) }
            pedirPermisos.launch(faltan.toTypedArray())
            return
        }
        if (!adaptador.isEnabled) {
            pendiente = accion
            mostrar(Textos.t("Enciende el Bluetooth para sincronizar."))
            pedirEncender.launch(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
            return
        }
        accion()
    }

    // ------------------------------------------------------------------ sincronizar
    private fun sincronizar() {
        val direccion = s.settings.pcDireccion ?: return buscar()
        asegurarBluetooth(buscando = false) {
            detenerBusqueda()
            ui = ui.copy(encontrados = emptyList(), mensaje = null)
            if (soloConectar) vm.probar(direccion) else vm.iniciar(direccion)
        }
    }

    // ------------------------------------------------------------------ buscar el PC (solo la primera vez)
    /** Cualquier operador elige o cambia el PC: no hay roles de supervisión en el teléfono. */
    private fun puedeCambiarPc(): Boolean = true

    private fun buscar() {
        if (vm.enCurso) return
        asegurarBluetooth(buscando = true) { iniciarBusqueda() }
    }

    private fun iniciarBusqueda() {
        val adaptador = s.conector.adaptador() ?: return
        vm.cancelar()  // deja el indicador en «buscando», no en el resultado anterior
        ui = ui.copy(buscando = true, encontrados = emptyList(), mensaje = null)
        adaptador.bondedDevices?.forEach { agregarPc(it.address, it.name) }
        if (!receptorActivo) {
            val filtro = IntentFilter().apply {
                addAction(BluetoothDevice.ACTION_FOUND)
                addAction(BluetoothDevice.ACTION_NAME_CHANGED)
                addAction(BluetoothAdapter.ACTION_DISCOVERY_FINISHED)
            }
            ContextCompat.registerReceiver(this, receptor, filtro, ContextCompat.RECEIVER_NOT_EXPORTED)
            receptorActivo = true
        }
        adaptador.startDiscovery()
    }

    private fun detenerBusqueda() {
        if (receptorActivo) {
            runCatching { unregisterReceiver(receptor) }
            receptorActivo = false
        }
        runCatching { s.conector.adaptador()?.cancelDiscovery() }
        if (ui.buscando) ui = ui.copy(buscando = false)
    }

    companion object {
        /** `true`: la app se abrió sin sesión y hay que conectar con el PC antes del acceso. */
        const val EXTRA_SOLO_CONECTAR = "solo_conectar"
    }

    private fun agregarPc(direccion: String, nombre: String?) {
        if (nombre != PcConnector.NOMBRE_PC || ui.encontrados.any { it.first == direccion }) return
        ui = ui.copy(encontrados = ui.encontrados + (direccion to nombre), mensaje = null)
    }
}
