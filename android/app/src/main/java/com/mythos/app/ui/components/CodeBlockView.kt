package com.mythos.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mythos.app.ui.theme.MythosColors

@Composable
fun CodeBlockView(
    code: String,
    language: String = "text",
    modifier: Modifier = Modifier,
) {
    val clipboardManager = LocalClipboardManager.current
    var copied by remember { mutableStateOf(false) }

    Surface(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp),
        shape = RoundedCornerShape(8.dp),
        color = MythosColors.Bg,
        border = BorderStroke(1.dp, MythosColors.Border),
    ) {
        Column {
            // Header: language label + copy button
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(MythosColors.Surface)
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = language.lowercase(),
                    color = MythosColors.Text2,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                TextButton(
                    onClick = {
                        clipboardManager.setText(AnnotatedString(code))
                        copied = true
                    },
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                ) {
                    Text(
                        text = if (copied) "Copied!" else "Copy",
                        color = if (copied) MythosColors.Success else MythosColors.Text2,
                        fontSize = 11.sp,
                    )
                }
            }

            HorizontalDivider(color = MythosColors.Border, thickness = 1.dp)

            // Code body
            SelectionContainer {
                Text(
                    text = code,
                    color = MythosColors.Text,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 13.sp,
                    lineHeight = 20.sp,
                    modifier = Modifier.padding(16.dp),
                )
            }
        }
    }
}
