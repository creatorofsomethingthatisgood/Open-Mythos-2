package com.mythos.app.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mythos.app.ui.theme.CodingMode
import com.mythos.app.ui.theme.MythosColors

@Composable
fun StatusBar(
    mode: CodingMode,
    engineName: String,
    tokenCount: Int,
    isGenerating: Boolean,
    modifier: Modifier = Modifier,
) {
    Surface(
        color = MythosColors.Surface,
        modifier = modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = mode.label,
                color = MythosColors.Accent2,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = engineName,
                color = MythosColors.Text3,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
            )
            Text(
                text = "${tokenCount}tok",
                color = MythosColors.Text3,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
            )
            if (isGenerating) {
                Text(
                    text = "...",
                    color = MythosColors.Accent2,
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                )
            }
            Spacer(modifier = Modifier.weight(1f))
            Text(
                text = "Mythos 2.0",
                color = MythosColors.Text3,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
            )
        }
    }
}
