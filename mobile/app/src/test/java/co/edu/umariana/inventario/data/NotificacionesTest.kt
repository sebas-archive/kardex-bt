package co.edu.umariana.inventario.data

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class NotificacionesTest {
    private lateinit var db: AppDatabase
    private lateinit var repo: NotificacionRepository
    private var ahora = 1_731_170_400_000L

    @Before
    fun abrir() {
        db = TestDb.abrir()
        repo = NotificacionRepository(db.notificaciones()) { ahora }
    }

    @After
    fun cerrar() = db.close()

    @Test
    fun crearListarYMarcarComoLeidas() {
        repo.crear(TipoAviso.SYNC_OK, "12", PantallaAviso.PENDIENTES)
        ahora += 1000
        repo.crear(TipoAviso.CUENTA_CREADA, "", PantallaAviso.ESTADO_CUENTA)
        assertEquals(2, repo.todas().size)
        assertEquals(2, repo.noLeidas())
        assertEquals(TipoAviso.CUENTA_CREADA, repo.todas().first().tipo)  // más reciente primero

        val primero = repo.todas().first()
        repo.marcar(primero.id)
        assertEquals(1, repo.noLeidas())
        assertTrue(db.notificaciones().todas().first { it.id == primero.id }.leida)

        repo.marcarTodas()
        assertEquals(0, repo.noLeidas())
        assertTrue(repo.todas().all { it.leida })
        assertFalse(repo.todas().isEmpty())
    }
}
