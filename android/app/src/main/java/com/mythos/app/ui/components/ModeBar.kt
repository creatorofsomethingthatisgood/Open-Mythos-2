package com.mythos.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mythos.app.ui.theme.CodingMode
import com.mythos.app.ui.theme.MythosColors

@Composable
fun ModeBar(
    currentMode: CodingMode,
    onModeChange: (CodingMode) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 12.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        CodingMode.entries.forEach { mode ->
            val isActive = mode == currentMode
            Surface(
                onClick = { onModeChange(mode) },
                shape = RoundedCornerShape(6.dp),
                color = if (isActive) MythosColors.AccentDim else MythosColors.Surface2,
                border = if (isActive) BorderStroke(1.dp, MythosColors.Accent) else BorderStroke(1.dp, MythosColors.Border),
                modifier = Modifier.defaultMinSize(minWidth = 56.dp),
            ) {
                Text(
                    text = mode.label,
                    color = if (isActive) MythosColors.Accent2 else MythosColors.Text2,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                )
            }
        }
    }
}
