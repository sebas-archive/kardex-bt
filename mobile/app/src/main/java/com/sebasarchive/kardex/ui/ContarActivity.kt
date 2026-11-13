package com.sebasarchive.kardex.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.sebasarchive.kardex.scan.CodigoEscaneado
import com.sebasarchive.kardex.ui.pantallas.ContarScreen
import com.sebasarchive.kardex.ui.pantallas.ContarUi
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.math.BigDecimal

/**
 * Contar: escanear (o digitar) el SKU, ver el producto, poner la cantidad con el teclado y +/−, y guardar.
 * Todo se guarda en el teléfono; no hace falta conexión. Con EXTRA_SKU se abre para corregir una lectura.
 */
class ContarActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private var ui by mutableStateOf(ContarUi(""))
    private var consulta: Job? = null

    private val escaner = registerForActivityResult(ScanContract()) { resultado ->
        val leido = resultado.contents ?: return@registerForActivityResult  // se canceló
        val sku = CodigoEscaneado.sku(leido)  // un código de barras ya es el SKU; de un QR se extrae
        if (sku.isEmpty()) aviso("Ese código no trae un SKU") else cambiarSku(sku, espera = 0)
    }
    private val pedirCamara = registerForActivityResult(ActivityResultContracts.RequestPermission()) { concedido ->
        if (concedido) lanzarEscaner() else aviso("Sin permiso de cámara: escribe el SKU a mano")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val conteo = s.contar.conteo.value
        if (conteo == null) { finish(); return }

        val skuACorregir = intent.getStringExtra(EXTRA_SKU)
        ui = ContarUi(conteo, edicion = skuACorregir != null,
            cantidad = intent.getStringExtra(EXTRA_CANTIDAD).orEmpty(), nota = intent.getStringExtra(EXTRA_NOTA).orEmpty())
        if (skuACorregir != null) cambiarSku(skuACorregir, espera = 0)

        pantalla {
            ContarScreen(
                ui,
                alCambiarSku = { cambiarSku(it) },
                alCambiarCantidad = { ui = ui.copy(cantidad = it, error = null) },
                alCambiarNota = { ui = ui.copy(nota = it, error = null) },
                alSumar = ::sumar,
                alEscanear = ::escanear,
                alGuardar = ::guardar,
                alVolver = { finish() },
            )
        }
    }

    private fun escanear() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) lanzarEscaner()
        else pedirCamara.launch(Manifest.permission.CAMERA)
    }

    private fun lanzarEscaner() = escaner.launch(
        ScanOptions()
            // Códigos de barras (EAN, UPC, Code 128…) y también el QR o el Data Matrix del producto.
            .setDesiredBarcodeFormats(ScanOptions.ONE_D_CODE_TYPES + ScanOptions.QR_CODE + ScanOptions.DATA_MATRIX)
            .setPrompt("Apunta al código de barras o al QR")
            .setBeepEnabled(true)
            .setOrientationLocked(false)
    )

    private fun sumar(paso: Int) {
        val actual = ui.cantidad.toBigDecimalOrNull() ?: BigDecimal.ZERO
        val nuevo = (actual + BigDecimal(paso)).max(BigDecimal.ZERO)
        ui = ui.copy(cantidad = nuevo.stripTrailingZeros().toPlainString(), error = null)
    }

    /**
     * Cambia el SKU y busca el producto y si ya se contó aquí (en ese caso guardar es recontar). Al teclear se espera
     * un momento para no marcar «fuera del catálogo» un código a medio escribir.
     */
    private fun cambiarSku(sku: String, espera: Long = 300) {
        ui = ui.copy(sku = sku, error = null)
        consulta?.cancel()
        consulta = lifecycleScope.launch {
            delay(espera)
            val (producto, previa) = withContext(Dispatchers.IO) { s.contar.producto(sku) to s.contar.ultimaLectura(sku) }
            ui = ui.copy(producto = producto, skuDesconocido = sku.isNotBlank() && producto == null, previa = previa?.cantidad)
        }
    }

    private fun guardar() {
        if (ui.exito) return  // todavía se está mostrando la confirmación del guardado anterior
        val actual = ui
        lifecycleScope.launch {
            val resultado = withContext(Dispatchers.IO) { s.contar.guardar(actual.sku, actual.cantidad, actual.nota) }
            if (resultado !is SaveResult.Guardada) {
                ui = ui.copy(error = resultado.mensaje())
                return@launch
            }
            if (resultado.reemplazo) aviso(resultado.mensaje())
            consulta?.cancel()
            ui = ui.copy(exito = true, error = null, guardadas = ui.guardadas + 1)
            delay(850)
            if (actual.edicion) finish()
            else ui = ContarUi(actual.conteo, guardadas = ui.guardadas)  // listo para el siguiente producto
        }
    }

    companion object {
        const val EXTRA_SKU = "sku"
        const val EXTRA_CANTIDAD = "cantidad"
        const val EXTRA_NOTA = "nota"
    }
}
