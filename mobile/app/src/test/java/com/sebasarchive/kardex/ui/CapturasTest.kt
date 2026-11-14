package com.sebasarchive.kardex.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import com.sebasarchive.kardex.auth.EstadoCuenta
import com.sebasarchive.kardex.auth.Rol
import com.sebasarchive.kardex.auth.Sesion
import com.sebasarchive.kardex.data.TareaEntity
import com.sebasarchive.kardex.data.Estado
import com.sebasarchive.kardex.data.ProductoEntity
import com.sebasarchive.kardex.ui.pantallas.ContarScreen
import com.sebasarchive.kardex.ui.pantallas.ContarUi
import com.sebasarchive.kardex.ui.pantallas.TareaFila
import com.sebasarchive.kardex.ui.pantallas.TareasScreen
import com.sebasarchive.kardex.ui.pantallas.HomeScreen
import com.sebasarchive.kardex.ui.pantallas.HomeUi
import com.sebasarchive.kardex.ui.pantallas.LecturaFila
import com.sebasarchive.kardex.ui.pantallas.LecturasScreen
import com.sebasarchive.kardex.ui.pantallas.PerfilScreen
import com.sebasarchive.kardex.ui.pantallas.PerfilUi
import com.sebasarchive.kardex.ui.pantallas.AuthScreen
import com.sebasarchive.kardex.ui.pantallas.AuthUi
import com.sebasarchive.kardex.ui.pantallas.DatosRegistro
import com.sebasarchive.kardex.ui.pantallas.ModoAuth
import com.sebasarchive.kardex.ui.pantallas.PendienteFila
import com.sebasarchive.kardex.ui.pantallas.PendientesScreen
import com.sebasarchive.kardex.ui.pantallas.SincronizarScreen
import com.sebasarchive.kardex.ui.pantallas.SincronizarUi
import com.sebasarchive.kardex.ui.theme.InventarioTheme
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File

/**
 * Dibuja cada pantalla con el motor gráfico real de Android (Robolectric en modo nativo) a tamaño de teléfono
 * (393 × 851 dp, 440 dpi → 1080 × 2340 px) y guarda un PNG en `build/capturas/`. Sirve de prueba de humo —todas las
 * pantallas componen con datos de ejemplo— y de fuente de las imágenes de `docs/img/movil/`.
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w393dp-h851dp-normal-long-notround-any-440dpi-keyshidden-nonav")
class CapturasTest {
    @get:Rule
    val compose = createComposeRule()

    private fun capturar(nombre: String, oscuro: Boolean = false, contenido: @Composable () -> Unit) {
        compose.setContent { InventarioTheme(oscuro = oscuro) { contenido() } }
        compose.mainClock.advanceTimeBy(1_500)  // deja terminar las animaciones de entrada
        val archivo = File("build/capturas/$nombre.png")
        archivo.parentFile?.mkdirs()
        compose.onRoot().captureRoboImage(archivo.path)
        assertTrue("no se generó $archivo", archivo.length() > 10_000)
    }

    private val cafe = ProductoEntity("7701234000012", "Café molido 500 g", "Abarrotes", "UND")
    private val home = HomeUi(operador = "Ana María", conteo = "CONT-2026-11", pendientes = 37, total = 112)
    private val pc = SincronizarUi(pcNombre = "gestion_inventario", pcDireccion = "DC:A6:32:4F:1B:22", pendientes = 37, puedeCambiarPc = false)

    private val ana = DatosRegistro(nombre = "Ana María Gómez", usuario = "ana.gomez", clave = "Conteo-2026", confirmacion = "Conteo-2026", respuesta = "Luna")

    @Composable
    private fun Acceso(ui: AuthUi, datos: DatosRegistro = ana) = AuthScreen(ui, {}, { _, _ -> }, {}, {}, { _, _, _, _ -> }, inicial = datos)

    @Test fun acceso_entrar() = capturar("01-acceso-entrar") { Acceso(AuthUi(), ana.copy(nombre = "", confirmacion = "", respuesta = "")) }

    @Test fun acceso_crear_cuenta() = capturar("02-acceso-crear-cuenta") { Acceso(AuthUi(modo = ModoAuth.REGISTRO)) }

    @Test fun acceso_recuperar() = capturar("03-acceso-recuperar") {
        Acceso(AuthUi(modo = ModoAuth.RECUPERAR, pregunta = "¿Cuál es el nombre de tu primera mascota?"))
    }

    @Test fun acceso_error() = capturar("04-acceso-clave-incorrecta") {
        Acceso(AuthUi(error = "Usuario o contraseña incorrectos", sacudida = 1), ana.copy(clave = "conteo2025"))
    }

    @Test fun acceso_bienvenida() = capturar("05-acceso-bienvenida") { Acceso(AuthUi(bienvenida = "Ana María Gómez")) }

    @Test fun inicio() = capturar("06-inicio") { HomeScreen(home, {}, {}, {}, {}, {}, {}) }

    @Test fun inicio_sin_catalogo() = capturar("07-inicio-primer-uso") {
        HomeScreen(HomeUi(operador = "Ana María", hayCatalogo = false), {}, {}, {}, {}, {}, {})
    }

    @Test fun mis_tareas() = capturar("08-mis-tareas") {
        TareasScreen(
            tareas = listOf(
                TareaFila(TareaEntity("T-014", "Bodega Norte, estantería A", "ALM-01", "Contar solo la estantería A, de arriba abajo",
                    "ENVIADA_PARCIALMENTE", 12, 7), iniciada = true, porRecontar = 2),
                TareaFila(TareaEntity("T-015", "Bebidas", "ALM-02", "", "ASIGNADA", 5, 0), iniciada = false, porRecontar = 0),
                TareaFila(TareaEntity("CONT-2026-11", "Inventario físico noviembre 2026", "", "", "", 0, 0), iniciada = false, porRecontar = 0),
            ),
            actual = "T-014", alIniciar = {}, alVolver = {}, alSincronizar = {},
        )
    }

    @Test fun mis_tareas_vacia() {
        capturar("08b-mis-tareas-vacia") {
            TareasScreen(tareas = emptyList(), actual = null, alIniciar = {}, alVolver = {}, alSincronizar = {})
        }
        compose.onNodeWithText("No tienes tareas asignadas").assertExists()
    }

    @Test fun contar() = capturar("09-contar") {
        ContarScreen(ContarUi("CONT-2026-11", sku = cafe.sku, cantidad = "24", producto = cafe, previa = "22", guardadas = 6),
            {}, {}, {}, {}, {}, {}, {})
    }

    @Test fun contar_con_foto() {
        val foto = File("build/capturas/evidencia.jpg").apply { parentFile?.mkdirs() }
        val bmp = android.graphics.Bitmap.createBitmap(400, 300, android.graphics.Bitmap.Config.ARGB_8888)
        android.graphics.Canvas(bmp).apply {
            drawColor(android.graphics.Color.rgb(176, 124, 72))
            drawRect(60f, 60f, 340f, 240f, android.graphics.Paint().apply { color = android.graphics.Color.rgb(120, 80, 40) })
        }
        foto.outputStream().use { bmp.compress(android.graphics.Bitmap.CompressFormat.JPEG, 80, it) }
        capturar("09b-contar-con-foto") {
            ContarScreen(ContarUi("T-014", sku = cafe.sku, cantidad = "24", producto = cafe, nota = "Caja rota en la estantería A",
                danados = "2", foto = foto.path), {}, {}, {}, {}, {}, {}, {})
        }
    }

    @Test fun contar_sku_desconocido() = capturar("10-contar-sku-desconocido") {
        ContarScreen(ContarUi("CONT-2026-11", sku = "7709990001234", cantidad = "3", skuDesconocido = true,
            nota = "Sin etiqueta de precio", guardadas = 7), {}, {}, {}, {}, {}, {}, {})
    }

    @Test fun contar_guardado() = capturar("11-contar-guardado") {
        ContarScreen(ContarUi("CONT-2026-11", sku = cafe.sku, cantidad = "24", producto = cafe, guardadas = 7, exito = true),
            {}, {}, {}, {}, {}, {}, {})
    }

    @Test fun contado_aqui() = capturar("12-contado-aqui") {
        LecturasScreen("CONT-2026-11", listOf(
            LecturaFila("7701234000012", "Café molido 500 g", "24", Estado.PENDIENTE, ""),
            LecturaFila("7701234000005", "Arroz blanco 1 kg", "40", Estado.PENDIENTE, "2 bolsas rotas"),
            LecturaFila("7701234000007", "Aceite vegetal 900 ml", "103", Estado.ENVIADO, ""),
            LecturaFila("7709990001234", null, "3", Estado.PENDIENTE, "Sin etiqueta de precio"),
            LecturaFila("7701234000002", "Azúcar blanca 1 kg", "201", Estado.CONFIRMADO, ""),
            LecturaFila("7701234000003", "Sal refinada 500 g", "83", Estado.CONFIRMADO, ""),
        ), {}, {}, {})
    }

    @Test fun pendientes() = capturar("13-pendientes") {
        val estados = listOf(Estado.PENDIENTE, Estado.PENDIENTE, Estado.PENDIENTE, Estado.ENVIADO, Estado.ENVIADO,
            Estado.CONFIRMADO, Estado.CONFIRMADO, Estado.CONFIRMADO, Estado.CONFIRMADO)
        PendientesScreen(estados.mapIndexed { i, estado ->
            PendienteFila((112 - i).toLong(), "77012340000${(12 + i * 7) % 60 + 10}", "${(i * 13 + 4) % 90 + 1}", estado)
        }, {}, {})
    }

    @Test fun sincronizar_buscar() = capturar("14-sincronizar-buscar") {
        SincronizarScreen(SincronizarUi(buscando = true, encontrados = listOf("DC:A6:32:4F:1B:22" to "gestion_inventario"), pendientes = 37), {}, {}, { _, _ -> }, {})
    }

    @Test fun sincronizar_conectando() = capturar("15-sincronizar-conectando") {
        SincronizarScreen(pc.copy(estado = SyncEstado.Conectando(1)), {}, {}, { _, _ -> }, {})
    }

    @Test fun sincronizar_enviando() = capturar("16-sincronizar-enviando") {
        SincronizarScreen(pc.copy(estado = SyncEstado.Sincronizando(100, 112), enviadas = 25, porEnviar = 37), {}, {}, { _, _ -> }, {})
    }

    @Test fun sincronizar_listo() = capturar("17-sincronizar-listo") {
        SincronizarScreen(pc.copy(estado = SyncEstado.Listo(37, 0, 0), pendientes = 0), {}, {}, { _, _ -> }, {})
    }

    @Test fun sincronizar_ocupado() = capturar("18-sincronizar-pc-ocupado") {
        SincronizarScreen(pc.copy(estado = SyncEstado.Ocupado), {}, {}, { _, _ -> }, {})
    }

    @Test fun sincronizar_sin_conexion() = capturar("19-sincronizar-sin-conexion") {
        SincronizarScreen(pc.copy(estado = SyncEstado.PcNoDisponible("read failed, socket might closed or timeout")), {}, {}, { _, _ -> }, {})
    }

    @Test fun mi_cuenta() = capturar("20-mi-cuenta") {
        PerfilScreen(Sesion("ana.gomez", "Ana María Gómez", Rol.OPERADOR, EstadoCuenta.ACTIVO, null), PerfilUi(), {}, { _, _, _ -> }, {}, {})
    }

    @Test fun inicio_oscuro() = capturar("21-inicio-oscuro", oscuro = true) { HomeScreen(home, {}, {}, {}, {}, {}, {}) }

    @Test fun contar_oscuro() = capturar("22-contar-oscuro", oscuro = true) {
        ContarScreen(ContarUi("CONT-2026-11", sku = cafe.sku, cantidad = "24", producto = cafe, previa = "22", guardadas = 6),
            {}, {}, {}, {}, {}, {}, {})
    }

    @Test fun acceso_oscuro() = capturar("23-acceso-oscuro", oscuro = true) { Acceso(AuthUi(), ana.copy(nombre = "", confirmacion = "", respuesta = "")) }
}
