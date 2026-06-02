package com.mythos.app.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.mythos.app.ui.theme.MythosColors

@Composable
fun InputBar(
    onSend: (String) -> Unit,
    isGenerating: Boolean,
    modifier: Modifier = Modifier,
) {
    var text by remember { mutableStateOf("") }

    Surface(
        color = MythosColors.Surface,
        modifier = modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.Bottom,
        ) {
            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                placeholder = { Text("Send a message...", color = MythosColors.Text3) },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = MythosColors.Accent,
                    unfocusedBorderColor = MythosColors.Border,
                    focusedContainerColor = MythosColors.Surface2,
                    unfocusedContainerColor = MythosColors.Surface2,
                    cursorColor = MythosColors.Accent2,
                    focusedTextColor = MythosColors.Text,
                    unfocusedTextColor = MythosColors.Text,
                ),
                maxLines = 6,
                enabled = !isGenerating,
            )

            Spacer(modifier = Modifier.width(8.dp))

            Button(
                onClick = {
                    if (text.isNotBlank()) {
                        onSend(text.trim())
                        text = ""
                    }
                },
                enabled = text.isNotBlank() && !isGenerating,
                colors = ButtonDefaults.buttonColors(
                    containerColor = MythosColors.Accent,
                    contentColor = MythosColors.Text,
                    disabledContainerColor = MythosColors.Border,
                    disabledContentColor = MythosColors.Text3,
                ),
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.size(48.dp),
                contentPadding = PaddingValues(0.dp),
            ) {
                if (isGenerating) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        color = MythosColors.Text2,
                        strokeWidth = 2.dp,
                    )
                } else {
                    Text(">", fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
                }
            }
        }
    }
}
