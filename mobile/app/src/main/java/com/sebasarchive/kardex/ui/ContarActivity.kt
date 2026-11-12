package com.sebasarchive.kardex.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.text.InputType
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.math.BigDecimal

/**
 * Contar: escanear (o digitar) el SKU, ver el producto, poner la cantidad con el teclado y +/−, y guardar.
 * Todo se guarda en el teléfono; no hace falta conexión. Con EXTRA_SKU se abre para corregir una lectura.
 */
class ContarActivity : PantallaActivity() {
    private val s by lazy { Servicios.de(this) }
    private lateinit var etSku: EditText
    private lateinit var etCantidad: EditText
    private lateinit var etNota: EditText
    private lateinit var tvProducto: TextView
    private lateinit var tvPrevio: TextView
    private var consulta: Job? = null
    private var edicion = false

    private val escaner = registerForActivityResult(ScanContract()) { resultado ->
        resultado.contents?.trim()?.takeIf { it.isNotEmpty() }?.let {
            etSku.setText(it)
            etCantidad.requestFocus()
        }
    }
    private val pedirCamara = registerForActivityResult(ActivityResultContracts.RequestPermission()) { concedido ->
        if (concedido) lanzarEscaner() else aviso("Sin permiso de cámara: escribe el SKU a mano")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        montar("Contar")
        val ubicacion = s.contar.ubicacion.value ?: run { finish(); return }
        edicion = intent.hasExtra(EXTRA_SKU)

        texto("Conteo ${s.contar.conteo.value} · Ubicación $ubicacion", 15f, negrita = true)
        etSku = campo("SKU o código de barras", 40, InputType.TYPE_CLASS_TEXT)
        boton("Escanear código de barras") { escanear() }
        tvProducto = texto("", 16f, negrita = true)
        tvPrevio = texto("", 14f)

        etCantidad = campo("Cantidad", 13, InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL)
        etCantidad.textSize = 28f
        val fila = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        for ((rotulo, paso) in listOf("−" to -1, "+" to 1)) {
            fila.addView(android.widget.Button(this).apply {
                text = rotulo
                textSize = 24f
                setOnClickListener { sumar(paso) }
            }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        }
        raiz.addView(fila)
        etNota = campo("Nota (opcional)", CountViewModel.MAX_NOTA)
        boton("Guardar") { guardar(ubicacion) }

        etSku.alCambiar { consultar(ubicacion, it) }
        intent.getStringExtra(EXTRA_SKU)?.let {
            etSku.setText(it)
            etSku.isEnabled = false  // se corrige la cantidad, no el producto
            etCantidad.setText(intent.getStringExtra(EXTRA_CANTIDAD) ?: "")
            etNota.setText(intent.getStringExtra(EXTRA_NOTA) ?: "")
        }
    }

    private fun escanear() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) lanzarEscaner()
        else pedirCamara.launch(Manifest.permission.CAMERA)
    }

    private fun lanzarEscaner() = escaner.launch(
        ScanOptions()
            .setDesiredBarcodeFormats(ScanOptions.ONE_D_CODE_TYPES)  // EAN, UPC, Code 128…: el código de barras es el SKU (D14)
            .setPrompt("Apunta al código de barras")
            .setBeepEnabled(true)
            .setOrientationLocked(false)
    )

    private fun sumar(paso: Int) {
        val actual = etCantidad.text.toString().toBigDecimalOrNull() ?: BigDecimal.ZERO
        val nuevo = (actual + BigDecimal(paso)).max(BigDecimal.ZERO)
        etCantidad.setText(nuevo.stripTrailingZeros().toPlainString())
        etCantidad.setSelection(etCantidad.text.length)
    }

    /** Muestra el producto del catálogo y si ya se contó aquí (en ese caso guardar es recontar). */
    private fun consultar(ubicacion: String, sku: String) {
        consulta?.cancel()
        consulta = lifecycleScope.launch {
            val (producto, previa) = withContext(Dispatchers.IO) {
                s.contar.producto(sku) to s.contar.ultimaLectura(ubicacion, sku)
            }
            tvProducto.text = when {
                sku.isBlank() -> ""
                producto != null -> "${producto.nombre} (${producto.unidad})"
                else -> "⚠ SKU fuera del catálogo: se puede guardar igual"
            }
            tvPrevio.text = previa?.let { "Ya contado aquí: ${it.cantidad}. Guardar lo reemplaza." } ?: ""
        }
    }

    private fun guardar(ubicacion: String) {
        val sku = etSku.text.toString()
        lifecycleScope.launch {
            val resultado = withContext(Dispatchers.IO) {
                s.contar.guardar(ubicacion, sku, etCantidad.text.toString(), etNota.text.toString())
            }
            if (resultado is SaveResult.Guardada && resultado.skuDesconocido) aviso("Guardado. ${resultado.mensaje()}\n⚠ El SKU no está en el catálogo")
            else aviso(resultado.mensaje())
            if (resultado !is SaveResult.Guardada) return@launch
            if (edicion) {
                finish()
            } else {  // listo para el siguiente producto
                etSku.setText("")
                etCantidad.setText("")
                etNota.setText("")
                etSku.requestFocus()
            }
        }
    }

    companion object {
        const val EXTRA_SKU = "sku"
        const val EXTRA_CANTIDAD = "cantidad"
        const val EXTRA_NOTA = "nota"
    }
}
