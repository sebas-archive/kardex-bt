package co.edu.umariana.inventario.ui

import android.graphics.Typeface
import android.text.Editable
import android.text.InputFilter
import android.text.TextWatcher
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

/** Base de las pantallas: una columna con desplazamiento y los controles de siempre. */
abstract class PantallaActivity : AppCompatActivity() {
    protected lateinit var raiz: LinearLayout

    protected fun montar(titulo: String) {
        title = titulo
        raiz = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(16), dp(16), dp(16))
        }
        setContentView(ScrollView(this).apply {
            isFillViewport = true
            addView(raiz, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        })
    }

    protected fun dp(valor: Int): Int = (valor * resources.displayMetrics.density).toInt()

    private fun <T : android.view.View> T.alAncho(arriba: Int = 8): T {
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            .apply { topMargin = dp(arriba) }
        return this
    }

    protected fun texto(contenido: String = "", tam: Float = 16f, negrita: Boolean = false): TextView =
        TextView(this).apply {
            text = contenido
            textSize = tam
            if (negrita) setTypeface(typeface, Typeface.BOLD)
            alAncho()
            raiz.addView(this)
        }

    protected fun boton(rotulo: String, alPulsar: () -> Unit): Button =
        Button(this).apply {
            text = rotulo
            setOnClickListener { alPulsar() }
            alAncho()
            raiz.addView(this)
        }

    protected fun campo(pista: String, maxCaracteres: Int, tipo: Int = android.text.InputType.TYPE_CLASS_TEXT): EditText =
        EditText(this).apply {
            hint = pista
            inputType = tipo
            filters = arrayOf(InputFilter.LengthFilter(maxCaracteres))
            alAncho()
            raiz.addView(this)
        }

    protected fun aviso(mensaje: String) = Toast.makeText(this, mensaje, Toast.LENGTH_LONG).show()

    protected fun EditText.alCambiar(accion: (String) -> Unit) {
        addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) = accion(s?.toString() ?: "")
        })
    }
}

/** El mensaje que ve el operario cuando no se pudo guardar. */
fun SaveResult.mensaje(): String = when (this) {
    is SaveResult.Guardada -> if (reemplazo) "Recuento guardado: reemplaza la lectura anterior" else "Guardado"
    SaveResult.OperadorFaltante -> "Escribe el nombre del operador (máximo ${CountViewModel.MAX_OPERADOR} caracteres)"
    SaveResult.SinConteo -> "Elige primero el conteo"
    SaveResult.UbicacionFaltante -> "Elige la ubicación"
    SaveResult.SkuFaltante -> "Escanea o escribe el SKU"
    SaveResult.CantidadInvalida -> "Cantidad inválida: usa números con punto decimal (hasta 9 enteros y 3 decimales)"
    SaveResult.NotaLarga -> "La nota admite hasta ${CountViewModel.MAX_NOTA} caracteres"
}
