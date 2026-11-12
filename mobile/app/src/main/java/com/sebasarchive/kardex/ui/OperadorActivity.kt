package com.sebasarchive.kardex.ui

import android.os.Bundle

/** Primer uso (y editable): quién cuenta. Obligatorio, máximo 60 caracteres, se recuerda. */
class OperadorActivity : PantallaActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        montar("Operador")
        val s = Servicios.de(this)
        texto("¿Quién está contando? Este nombre se guarda con cada lectura.")
        val nombre = campo("Nombre del operador", CountViewModel.MAX_OPERADOR)
        nombre.setText(s.contar.operador.value)
        boton("Guardar") {
            s.contar.setOperador(nombre.text.toString())
            if (s.contar.operador.value.isEmpty()) aviso("Escribe un nombre (máximo ${CountViewModel.MAX_OPERADOR} caracteres)")
            else finish()
        }
    }
}
