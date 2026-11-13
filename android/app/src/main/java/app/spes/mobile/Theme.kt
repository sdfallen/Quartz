package app.spes.mobile

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** Same tokens as the desktop (ui/styles.py): calm ink ground, paper text, sage accent. */
object SpesColors {
    val bg = Color(0xFF121416)
    val surface1 = Color(0xFF181B1D)
    val surface2 = Color(0xFF1F2326)
    val surface3 = Color(0xFF2A2F32)
    val line = Color(0x26E2ECE6)
    val text = Color(0xFFEEF1ED)
    val text2 = Color(0xFFC4CBC6)
    val text3 = Color(0xFF98A29C)
    val accent = Color(0xFF8FCFB0)
    val onAccent = Color(0xFF0F2A1E)
    val danger = Color(0xFFF28B82)
    val stop = Color(0xFFB93A30)
    val fatum = Color(0xFFE8A06E)
    val fides = Color(0xFF8AB4F8)
    val eos = Color(0xFFF2A7C0)

    fun persona(name: String): Color = when (name) {
        "Fatum" -> fatum
        "Fides" -> fides
        "Eos" -> eos
        else -> text2
    }
}

@Composable
fun SpesTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = SpesColors.accent, onPrimary = SpesColors.onAccent,
            background = SpesColors.bg, onBackground = SpesColors.text,
            surface = SpesColors.surface1, onSurface = SpesColors.text,
            surfaceVariant = SpesColors.surface2, onSurfaceVariant = SpesColors.text2,
            outline = SpesColors.surface3, error = SpesColors.danger,
        ),
        content = content,
    )
}
