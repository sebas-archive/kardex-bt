package co.edu.umariana.inventario.auth

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import co.edu.umariana.inventario.ui.SettingsStore
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

private const val PREGUNTA = "¿Cuál es el nombre de tu primera mascota?"

@RunWith(RobolectricTestRunner::class)
class AuthRepositoryTest {
    private lateinit var db: CuentasDatabase
    private lateinit var settings: SettingsStore
    private lateinit var auth: AuthRepository
    private var ahora = 1_731_170_400_000L

    private fun nuevo() = AuthRepository(db.usuarios(), settings, { ahora }, iteraciones = 1_000)  // pocas vueltas: la prueba no mide la lentitud

    @Before
    fun abrir() {
        db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext(), CuentasDatabase::class.java)
            .allowMainThreadQueries().build()
        settings = SettingsStore(ApplicationProvider.getApplicationContext())
        auth = nuevo()
    }

    @After
    fun cerrar() = db.close()

    private fun registrarAna() =
        auth.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026", PREGUNTA, "Luna")

    @Test
    fun registroNuevoQuedaPendiente() {
        val resultado = auth.registrar("  Ana.Gomez ", " Ana Gómez ", "conteo2026", "conteo2026", PREGUNTA, "Luna")
        val usuario = (resultado as AuthResult.Ok).usuario
        assertEquals("ana.gomez", usuario.usuario)  // el usuario se guarda en minúsculas y sin espacios
        assertEquals("Ana Gómez", usuario.nombre)
        assertEquals(Rol.OPERADOR, usuario.rol)       // en el teléfono solo hay operadores
        assertEquals(EstadoCuenta.PENDIENTE, usuario.estado)  // hasta que el administrador la apruebe en el PC
        val esperada = Sesion("ana.gomez", "Ana Gómez", Rol.OPERADOR, EstadoCuenta.PENDIENTE, null)
        assertEquals(esperada, auth.sesion())
        assertEquals(esperada, nuevo().sesion())  // la sesión sobrevive a cerrar la app
        assertFalse(esperada.puedeTrabajar)
    }

    @Test
    fun aplicarEstadoActivoDejaEntrar() {
        registrarAna()
        auth.aplicarEstado("ana.gomez", EstadoCuenta.ACTIVO, Rol.OPERADOR, null)
        assertEquals(EstadoCuenta.ACTIVO, auth.sesion()?.estado)  // la sesión abierta se entera sin volver a entrar
        assertTrue(auth.sesion()!!.puedeTrabajar)
        auth.cerrarSesion()
        val ok = auth.iniciarSesion("ana.gomez", "conteo2026") as AuthResult.Ok
        assertEquals(EstadoCuenta.ACTIVO, ok.usuario.estado)
    }

    @Test
    fun aplicarEstadoRechazadoGuardaElMotivo() {
        registrarAna()
        auth.aplicarEstado("ana.gomez", EstadoCuenta.RECHAZADO, null, "No trabaja | en la bodega")
        assertEquals(Sesion("ana.gomez", "Ana Gómez", Rol.OPERADOR, EstadoCuenta.RECHAZADO, "No trabaja | en la bodega"), auth.sesion())
        auth.cerrarSesion()
        val ok = auth.iniciarSesion("ana.gomez", "conteo2026") as AuthResult.Ok  // la clave es correcta: la pantalla muestra el estado
        assertEquals("No trabaja | en la bodega", ok.usuario.motivo)
        auth.aplicarEstado("nadie", EstadoCuenta.ACTIVO, Rol.OPERADOR, null)  // cuenta que no existe: no hace nada
    }

    @Test
    fun test_register_validates_every_field() {
        fun r(usuario: String = "luis", nombre: String = "Luis", clave: String = "conteo2026", confirmacion: String = clave,
              pregunta: String = PREGUNTA, respuesta: String = "Luna") = auth.registrar(usuario, nombre, clave, confirmacion, pregunta, respuesta)
        assertEquals(AuthResult.UsuarioInvalido, r(usuario = "lu"))
        assertEquals(AuthResult.UsuarioInvalido, r(usuario = "luis pérez"))
        assertEquals(AuthResult.UsuarioInvalido, r(usuario = "x".repeat(21)))
        assertEquals(AuthResult.NombreInvalido, r(nombre = "  "))
        assertEquals(AuthResult.NombreInvalido, r(nombre = "n".repeat(61)))  // el nombre es el operador de cada lectura: máx. 60
        assertEquals(AuthResult.ClaveDebil, r(clave = "abc123"))             // menos de 8
        assertEquals(AuthResult.ClaveDebil, r(clave = "solamenteletras"))    // sin números
        assertEquals(AuthResult.ClaveDebil, r(clave = "1234567890"))         // sin letras
        assertEquals(AuthResult.ClavesDistintas, r(confirmacion = "conteo2027"))
        assertEquals(AuthResult.PreguntaFaltante, r(pregunta = " "))
        assertEquals(AuthResult.RespuestaCorta, r(respuesta = " a "))
        assertNull(auth.sesion())
        assertTrue(db.usuarios().todos().isEmpty())

        assertTrue(r() is AuthResult.Ok)
        assertEquals(AuthResult.UsuarioExiste, r(usuario = "LUIS", nombre = "Otro Luis"))  // sin distinguir mayúsculas
        assertEquals(1, db.usuarios().todos().size)
    }

    @Test
    fun test_password_and_answer_are_never_stored_in_plain_text() {
        registrarAna()
        auth.registrar("luis", "Luis", "conteo2026", "conteo2026", PREGUNTA, "Luna")
        val (ana, luis) = db.usuarios().todos()
        for (u in listOf(ana, luis)) {
            assertFalse(u.claveHash.contains("conteo2026"))
            assertFalse(u.respuestaHash.contains("luna", ignoreCase = true))
            assertTrue(u.claveHash.startsWith("pbkdf2-sha1$1000$"))
        }
        assertNotEquals(ana.claveHash, luis.claveHash)  // misma clave, sal distinta
    }

    @Test
    fun test_login_accepts_the_right_password_only() {
        registrarAna()
        auth.cerrarSesion()
        assertNull(auth.sesion())

        assertEquals(AuthResult.CredencialesInvalidas, auth.iniciarSesion("ana.gomez", "Conteo2026"))
        assertEquals(AuthResult.CredencialesInvalidas, auth.iniciarSesion("nadie", "conteo2026"))  // mismo mensaje: no revela si existe
        assertNull(auth.sesion())

        assertTrue(auth.iniciarSesion(" ANA.gomez ", "conteo2026") is AuthResult.Ok)
        assertEquals("Ana Gómez", auth.sesion()?.nombre)
    }

    @Test
    fun test_login_locks_for_30_seconds_after_5_failures() {
        registrarAna()
        auth.cerrarSesion()
        repeat(4) { assertEquals(AuthResult.CredencialesInvalidas, auth.iniciarSesion("ana.gomez", "malaclave1")) }
        assertEquals(AuthResult.Bloqueado(30), auth.iniciarSesion("ana.gomez", "malaclave1"))  // el quinto fallo bloquea
        ahora += 10_000
        assertEquals(AuthResult.Bloqueado(20), auth.iniciarSesion("ana.gomez", "conteo2026"))  // ni con la clave buena
        ahora += 20_000
        assertTrue(auth.iniciarSesion("ana.gomez", "conteo2026") is AuthResult.Ok)
        auth.cerrarSesion()
        repeat(4) { auth.iniciarSesion("ana.gomez", "malaclave1") }  // un acierto había puesto el contador en cero
        assertTrue(auth.iniciarSesion("ana.gomez", "conteo2026") is AuthResult.Ok)
    }

    @Test
    fun test_forgot_password_resets_with_the_security_answer() {
        registrarAna()
        auth.cerrarSesion()
        assertEquals(PREGUNTA, auth.preguntaDe(" Ana.Gomez "))
        assertNull(auth.preguntaDe("nadie"))

        assertEquals(AuthResult.UsuarioNoExiste, auth.restablecer("nadie", "Luna", "nueva2027", "nueva2027"))
        assertEquals(AuthResult.RespuestaIncorrecta, auth.restablecer("ana.gomez", "Sol", "nueva2027", "nueva2027"))
        assertEquals(AuthResult.ClaveDebil, auth.restablecer("ana.gomez", "Luna", "corta1", "corta1"))
        assertEquals(AuthResult.ClavesDistintas, auth.restablecer("ana.gomez", "Luna", "nueva2027", "nueva2028"))
        assertTrue(auth.iniciarSesion("ana.gomez", "conteo2026") is AuthResult.Ok)  // nada cambió todavía
        auth.cerrarSesion()

        assertTrue(auth.restablecer("ana.gomez", "  LUNA ", "nueva2027", "nueva2027") is AuthResult.Ok)  // la respuesta no distingue mayúsculas
        assertNull(auth.sesion())  // restablecer no abre sesión: se entra con la clave nueva
        assertEquals(AuthResult.CredencialesInvalidas, auth.iniciarSesion("ana.gomez", "conteo2026"))
        assertTrue(auth.iniciarSesion("ana.gomez", "nueva2027") is AuthResult.Ok)
    }

    @Test
    fun test_wrong_answers_also_lock_the_account() {
        registrarAna()
        auth.cerrarSesion()
        repeat(4) { assertEquals(AuthResult.RespuestaIncorrecta, auth.restablecer("ana.gomez", "Sol", "nueva2027", "nueva2027")) }
        assertEquals(AuthResult.Bloqueado(30), auth.restablecer("ana.gomez", "Sol", "nueva2027", "nueva2027"))
        assertEquals(AuthResult.Bloqueado(30), auth.restablecer("ana.gomez", "Luna", "nueva2027", "nueva2027"))
    }

    @Test
    fun test_change_password_requires_the_current_one() {
        registrarAna()
        assertEquals(AuthResult.CredencialesInvalidas, auth.cambiarClave("otra12345", "nueva2027", "nueva2027"))
        assertEquals(AuthResult.ClaveDebil, auth.cambiarClave("conteo2026", "corta", "corta"))
        assertTrue(auth.cambiarClave("conteo2026", "nueva2027", "nueva2027") is AuthResult.Ok)
        auth.cerrarSesion()
        assertEquals(AuthResult.SinSesion, auth.cambiarClave("nueva2027", "otra12345", "otra12345"))
        assertTrue(auth.iniciarSesion("ana.gomez", "nueva2027") is AuthResult.Ok)
    }

    @Test
    fun test_password_strength_grows_with_length_and_variety() {
        assertEquals(0, Claves.fuerza(""))
        assertTrue(Claves.fuerza("abc") < Claves.fuerza("conteo2026"))
        assertTrue(Claves.fuerza("conteo2026") < Claves.fuerza("Conteo-2026-Bodega!"))
        assertTrue(Claves.fuerza("Conteo-2026-Bodega!") <= 4)
    }
}
