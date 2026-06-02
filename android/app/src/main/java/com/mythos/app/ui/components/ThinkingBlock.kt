package com.mythos.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mythos.app.ui.theme.MythosColors

@Composable
fun ThinkingBlock(
    reasoning: String,
    modifier: Modifier = Modifier,
) {
    var expanded by remember { mutableStateOf(false) }
    val wordCount = reasoning.split("\\s+".toRegex()).filter { it.isNotBlank() }.size

    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(8.dp),
        color = MythosColors.Surface,
        border = BorderStroke(1.dp, MythosColors.Border),
    ) {
        Column {
            // Toggle header
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { expanded = !expanded }
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "Thinking",
                    color = MythosColors.Accent2,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "$wordCount words",
                    color = MythosColors.Text3,
                    fontSize = 11.sp,
                )
                Spacer(modifier = Modifier.weight(1f))
                Text(
                    text = if (expanded) "-" else "+",
                    color = MythosColors.Accent2,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                )
            }

            if (expanded) {
                HorizontalDivider(color = MythosColors.Border, thickness = 1.dp)
                Text(
                    text = reasoning,
                    color = MythosColors.Text2,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 12.sp,
                    lineHeight = 18.sp,
                    modifier = Modifier.padding(12.dp, 16.dp),
                )
            }
        }
    }
}
