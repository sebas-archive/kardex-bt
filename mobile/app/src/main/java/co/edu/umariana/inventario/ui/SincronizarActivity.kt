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
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import co.edu.umariana.inventario.sync.PcConnector
import kotlinx.coroutines.launch

/**
 * Sincronizar (D22): si ya se eligió el PC, conecta de inmediato —sin buscar, sin emparejar, sin códigos—. La primera
 * vez busca «gestion_inventario» y se elige. Reintenta solo si se corta; avisa si el PC está ocupado o no responde.
 */
@SuppressLint("MissingPermission")  // los permisos se piden en `asegurarBluetooth` antes de tocar el adaptador
class SincronizarActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private val vm: SyncViewModel by viewModels { SyncViewModelFactory(Servicios.de(this)) }
    private lateinit var tvPc: TextView
    private lateinit var tvEstado: TextView
    private lateinit var barra: ProgressBar
    private lateinit var btnSincronizar: Button
    private lateinit var listaPcs: LinearLayout
    private var pendiente: (() -> Unit)? = null
    private var receptorActivo = false
    private val encontrados = mutableSetOf<String>()

    private val pedirPermisos = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { resultado ->
        if (resultado.values.all { it }) pendiente?.invoke()
        else mostrar("Sin permiso de Bluetooth. Actívalo en Ajustes > Aplicaciones > Inventario > Permisos.")
    }
    private val pedirEncender = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        if (s.conector.adaptador()?.isEnabled == true) pendiente?.invoke() else mostrar("El Bluetooth sigue apagado")
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
                BluetoothAdapter.ACTION_DISCOVERY_FINISHED ->
                    if (encontrados.isEmpty()) mostrar(
                        "No encontré «${PcConnector.NOMBRE_PC}». En el PC pulsa «Iniciar sincronización» y acércate. " +
                            "En Android 10 o anterior la ubicación del teléfono debe estar encendida para buscar.")
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        montar("Sincronizar")
        tvPc = texto("", 15f)
        tvEstado = texto("", 18f, negrita = true)
        barra = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).also { raiz.addView(it) }
        barra.visibility = android.view.View.GONE
        btnSincronizar = boton("Sincronizar ahora") { sincronizar() }
        boton("Buscar otro PC") { buscar() }
        listaPcs = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        raiz.addView(listaPcs)

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) { vm.estado.collect { dibujar(it) } }
        }
        actualizarPc()
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

    private fun actualizarPc() {
        val direccion = s.settings.pcDireccion
        tvPc.text = if (direccion == null) "Todavía no hay un PC elegido." else "PC: ${s.settings.pcNombre ?: PcConnector.NOMBRE_PC} ($direccion)"
    }

    private fun mostrar(mensaje: String) {
        tvEstado.text = mensaje
    }

    // ------------------------------------------------------------------ permisos y Bluetooth encendido
    private fun asegurarBluetooth(buscando: Boolean, accion: () -> Unit) {
        val adaptador = s.conector.adaptador() ?: return mostrar("Este teléfono no tiene Bluetooth")
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
            mostrar("Enciende el Bluetooth para sincronizar")
            pedirEncender.launch(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
            return
        }
        accion()
    }

    // ------------------------------------------------------------------ sincronizar
    private fun sincronizar() {
        val direccion = s.settings.pcDireccion ?: return buscar()
        listaPcs.removeAllViews()
        asegurarBluetooth(buscando = false) { vm.iniciar(direccion) }
    }

    private fun dibujar(estado: SyncEstado?) {
        val enCurso = estado is SyncEstado.Conectando || estado is SyncEstado.Sincronizando || estado is SyncEstado.Reintentando
        btnSincronizar.isEnabled = !enCurso
        barra.visibility = if (estado is SyncEstado.Sincronizando) android.view.View.VISIBLE else android.view.View.GONE
        tvEstado.text = when (estado) {
            null -> tvEstado.text
            is SyncEstado.Conectando -> "Conectando con el PC… (intento ${estado.intento})"
            is SyncEstado.Sincronizando -> {
                barra.max = estado.total.toInt()
                barra.progress = estado.confirmadoHasta.toInt()
                "Enviando… ${estado.confirmadoHasta} de ${estado.total}"
            }
            is SyncEstado.Reintentando -> "Se cortó (${estado.motivo}). Reintentando, intento ${estado.intento}…"
            is SyncEstado.Listo -> "Listo: ${estado.aceptados} lecturas aceptadas, ${estado.rechazados} rechazadas" +
                if (estado.pendientes > 0) ". Quedan ${estado.pendientes} sin enviar: vuelve a sincronizar." else ". Todo enviado."
            SyncEstado.Ocupado -> "El PC está atendiendo a otro teléfono. Espera a que termine y vuelve a intentar."
            is SyncEstado.Rechazado -> "El PC rechazó la conexión: ${estado.motivo}"
            is SyncEstado.PcNoDisponible -> "No se pudo conectar con el PC (${estado.motivo}). ¿Está encendido, cerca, " +
                "y con la sincronización iniciada en la aplicación?"
            is SyncEstado.Cortado -> "Se cortó la conexión (${estado.motivo}). Las ${estado.pendientes} lecturas sin enviar " +
                "siguen guardadas; vuelve a intentar."
        }
    }

    // ------------------------------------------------------------------ buscar el PC (solo la primera vez)
    private fun buscar() {
        asegurarBluetooth(buscando = true) { iniciarBusqueda() }
    }

    private fun iniciarBusqueda() {
        val adaptador = s.conector.adaptador() ?: return
        listaPcs.removeAllViews()
        encontrados.clear()
        mostrar("Buscando «${PcConnector.NOMBRE_PC}»… En el PC pulsa «Iniciar sincronización».")
        adaptador.bondedDevices?.forEach { if (it.name == PcConnector.NOMBRE_PC) agregarPc(it.address, it.name) }
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
    }

    private fun agregarPc(direccion: String, nombre: String?) {
        if (nombre != PcConnector.NOMBRE_PC || !encontrados.add(direccion)) return
        mostrar("Encontré el PC. Tócalo para conectar.")
        listaPcs.addView(Button(this).apply {
            text = "$nombre\n$direccion"
            setOnClickListener {
                s.settings.pcDireccion = direccion
                s.settings.pcNombre = nombre
                detenerBusqueda()
                actualizarPc()
                sincronizar()
            }
        })
    }
}
