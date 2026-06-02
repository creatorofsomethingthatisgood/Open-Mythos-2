package com.mythos.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable

private val DarkColorScheme = darkColorScheme(
    primary = MythosColors.Accent,
    onPrimary = MythosColors.Text,
    primaryContainer = MythosColors.AccentDark,
    onPrimaryContainer = MythosColors.AccentLight,
    secondary = MythosColors.Accent2,
    onSecondary = MythosColors.Text,
    secondaryContainer = MythosColors.Surface3,
    tertiary = MythosColors.Info,
    background = MythosColors.Bg,
    onBackground = MythosColors.Text,
    surface = MythosColors.Surface,
    onSurface = MythosColors.Text,
    surfaceVariant = MythosColors.Surface2,
    onSurfaceVariant = MythosColors.Text2,
    outline = MythosColors.Border,
    outlineVariant = MythosColors.Border2,
    error = MythosColors.Error,
    onError = MythosColors.Text,
    errorContainer = Color(0x33F85149),
    onErrorContainer = MythosColors.Error,
)

@Composable
fun MythosTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkColorScheme,
        typography = Typography(),
        content = content,
    )
}
