package co.edu.umariana.inventario

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.util.UUID

@RunWith(RobolectricTestRunner::class)
class DeviceIdentityTest {

    @Test
    fun test_uuid_generated_once_and_persisted() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val prefs = context.getSharedPreferences(DeviceIdentity.PREFS, Context.MODE_PRIVATE)

        val first = DeviceIdentity.get(context)
        assertEquals(first, UUID.fromString(first).toString())  // un UUID bien formado
        assertEquals(first, DeviceIdentity.get(context))        // siempre el mismo
        assertEquals(first, prefs.getString(DeviceIdentity.KEY, null))  // guardado en disco, no solo en memoria

        // Instalación nueva (datos borrados) = identidad nueva (D18).
        prefs.edit().clear().commit()
        val second = DeviceIdentity.get(context)
        assertNotEquals(first, second)
        assertEquals(second, DeviceIdentity.get(context))
    }
}
