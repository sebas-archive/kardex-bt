package com.sebasarchive.kardex.ui

import com.sebasarchive.kardex.sync.BluetoothSocketLike
import com.sebasarchive.kardex.sync.SyncProgress
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import java.io.IOException

/** Lo que la pantalla «Sincronizar» muestra. */
sealed class SyncEstado {
    data class Conectando(val intento: Int) : SyncEstado()
    data class Sincronizando(val confirmadoHasta: Long, val total: Long) : SyncEstado()
    data class Reintentando(val motivo: String, val intento: Int) : SyncEstado()
    /** Terminó con `BYE`. Si [pendientes] > 0 quedó algo por enviar. */
    data class Listo(val aceptados: Int, val rechazados: Int, val pendientes: Int) : SyncEstado()
    /** El PC está atendiendo a otro teléfono (D19). */
    data object Ocupado : SyncEstado()
    data class Rechazado(val motivo: String) : SyncEstado()
    /** No se pudo abrir la conexión: PC apagado, fuera de alcance o sin la sincronización iniciada. */
    data class PcNoDisponible(val motivo: String) : SyncEstado()
    data class Cortado(val motivo: String, val pendientes: Int) : SyncEstado()
    /** La cuenta no está activa en el PC: no se envió nada. No se reintenta: hay que esperar al administrador. */
    data class CuentaNoActiva(val estado: String, val motivo: String?, val pendientes: Int) : SyncEstado()
}

/**
 * Política de reintentos sobre [SyncClient]: conecta, sincroniza y, si se cortó o quedaron lecturas, vuelve a
 * intentar hasta [maxIntentos] veces. Reintentar es seguro: el `READY` del PC dice dónde reanudar (sin duplicados).
 * Un PC ocupado no se reintenta: cambia el resultado de la espera, no el de insistir.
 */
class SyncRunner(
    private val conectar: suspend (intento: Int) -> BluetoothSocketLike,
    private val sincronizar: (BluetoothSocketLike) -> Flow<SyncProgress>,
    private val maxIntentos: Int = 3,
    private val pausaMs: Long = 3_000,
) {
    fun ejecutar(): Flow<SyncEstado> = flow {
        var intento = 1
        while (true) {
            emit(SyncEstado.Conectando(intento))
            val socket = try {
                conectar(intento)
            } catch (e: IOException) {
                val motivo = e.message ?: e.javaClass.simpleName
                if (intento >= maxIntentos) {
                    emit(SyncEstado.PcNoDisponible(motivo))
                    return@flow
                }
                intento++
                emit(SyncEstado.Reintentando(motivo, intento))
                delay(pausaMs)
                continue
            }

            var terminal: SyncEstado? = null
            var reintentarPor: String? = null
            sincronizar(socket).collect { progreso ->
                when (progreso) {
                    is SyncProgress.Connected ->
                        emit(SyncEstado.Sincronizando(progreso.ultimoSeqServidor, progreso.ultimoSeqServidor + progreso.porEnviar))
                    is SyncProgress.Progress -> emit(SyncEstado.Sincronizando(progreso.confirmadoHasta, progreso.total))
                    is SyncProgress.Done ->
                        if (progreso.pendientes > 0 && intento < maxIntentos) {
                            reintentarPor = "Quedaron ${progreso.pendientes} lecturas por enviar"
                        } else {
                            terminal = SyncEstado.Listo(progreso.aceptados, progreso.rechazados, progreso.pendientes)
                        }
                    SyncProgress.Busy -> terminal = SyncEstado.Ocupado
                    is SyncProgress.CuentaNoActiva ->
                        terminal = SyncEstado.CuentaNoActiva(progreso.estado, progreso.motivo, progreso.pendientes)
                    is SyncProgress.Rejected -> terminal = SyncEstado.Rechazado(progreso.motivo)
                    is SyncProgress.Cut ->
                        if (intento < maxIntentos) reintentarPor = progreso.motivo
                        else terminal = SyncEstado.Cortado(progreso.motivo, progreso.pendientes)
                }
            }
            terminal?.let {
                emit(it)
                return@flow
            }
            intento++
            emit(SyncEstado.Reintentando(reintentarPor ?: "la conexión terminó sin respuesta", intento))
            delay(pausaMs)
        }
    }
}
