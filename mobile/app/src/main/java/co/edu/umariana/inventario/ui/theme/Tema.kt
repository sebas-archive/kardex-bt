package co.edu.umariana.inventario.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Colores de la marca y de los estados de una lectura (los mismos tonos que usa la app de escritorio). */
object Marca {
    val Verde = Color(0xFF0E7C66)
    val VerdeProfundo = Color(0xFF07503F)
    val Pendiente = Color(0xFFF79009)
    val Enviado = Color(0xFF2E90FA)
    val Confirmado = Color(0xFF12B76A)
}

private val Claro = lightColorScheme(
    primary = Marca.Verde, onPrimary = Color.White,
    primaryContainer = Color(0xFFCDEFE5), onPrimaryContainer = Color(0xFF00382D),
    secondary = Color(0xFFB45309), onSecondary = Color.White,
    secondaryContainer = Color(0xFFFFE8C7), onSecondaryContainer = Color(0xFF4A2800),
    tertiary = Color(0xFF3B5BDB), onTertiary = Color.White,
    tertiaryContainer = Color(0xFFDDE4FF), onTertiaryContainer = Color(0xFF0B1F66),
    background = Color(0xFFF4F7F6), onBackground = Color(0xFF16201D),
    surface = Color.White, onSurface = Color(0xFF16201D),
    surfaceVariant = Color(0xFFE6EDEA), onSurfaceVariant = Color(0xFF4A5753),
    outline = Color(0xFF8A9793), outlineVariant = Color(0xFFD3DCD8),
    error = Color(0xFFD92D20), onError = Color.White,
    errorContainer = Color(0xFFFEE4E2), onErrorContainer = Color(0xFF7A271A),
)

private val Oscuro = darkColorScheme(
    primary = Color(0xFF5FD9BE), onPrimary = Color(0xFF00382D),
    primaryContainer = Color(0xFF0B5F4E), onPrimaryContainer = Color(0xFFCDEFE5),
    secondary = Color(0xFFFFB95C), onSecondary = Color(0xFF4A2800),
    secondaryContainer = Color(0xFF6B3C00), onSecondaryContainer = Color(0xFFFFE8C7),
    tertiary = Color(0xFFB7C4FF), onTertiary = Color(0xFF0B1F66),
    tertiaryContainer = Color(0xFF2A419F), onTertiaryContainer = Color(0xFFDDE4FF),
    background = Color(0xFF0F1513), onBackground = Color(0xFFE1E8E5),
    surface = Color(0xFF18201D), onSurface = Color(0xFFE1E8E5),
    surfaceVariant = Color(0xFF26302C), onSurfaceVariant = Color(0xFFB4C0BC),
    outline = Color(0xFF7E8B87), outlineVariant = Color(0xFF36413D),
    error = Color(0xFFFF8A80), onError = Color(0xFF5F1410),
    errorContainer = Color(0xFF7A271A), onErrorContainer = Color(0xFFFEE4E2),
)

private val Formas = Shapes(
    small = RoundedCornerShape(10.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(24.dp),
    extraLarge = RoundedCornerShape(32.dp),
)

private val Base = Typography()
private val Letras = Typography(
    displayLarge = Base.displayLarge.copy(fontWeight = FontWeight.Bold),
    displayMedium = Base.displayMedium.copy(fontWeight = FontWeight.Bold),
    headlineSmall = Base.headlineSmall.copy(fontWeight = FontWeight.Bold),
    titleLarge = Base.titleLarge.copy(fontWeight = FontWeight.Bold),
    titleMedium = Base.titleMedium.copy(fontWeight = FontWeight.SemiBold),
    labelLarge = Base.labelLarge.copy(fontWeight = FontWeight.SemiBold, fontSize = 15.sp),
)

/** Cifras grandes con dígitos de ancho fijo: no «bailan» cuando cambia el número. */
val Cifra = TextStyle(fontWeight = FontWeight.Bold, fontFeatureSettings = "tnum")

@Composable
fun InventarioTheme(oscuro: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (oscuro) Oscuro else Claro, typography = Letras, shapes = Formas, content = content)
}
