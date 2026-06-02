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
import com.mythos.app.ui.theme.MythosColors

private val QUICK_ACTIONS = listOf(
    "Explain", "Review", "Optimize", "Test", "Document", "Refactor", "Security", "TypeScript",
)

@Composable
fun QuickActions(
    onAction: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 12.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        QUICK_ACTIONS.forEach { action ->
            OutlinedButton(
                onClick = { onAction(action) },
                shape = RoundedCornerShape(6.dp),
                border = BorderStroke(1.dp, MythosColors.Border),
                colors = ButtonDefaults.outlinedButtonColors(
                    containerColor = MythosColors.Surface2,
                    contentColor = MythosColors.Text2,
                ),
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                modifier = Modifier.defaultMinSize(minWidth = 1.dp, minHeight = 1.dp),
            ) {
                Text(action, fontSize = 11.sp, fontWeight = FontWeight.Normal)
            }
        }
    }
}
