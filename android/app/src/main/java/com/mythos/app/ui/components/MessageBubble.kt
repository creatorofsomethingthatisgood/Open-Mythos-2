package com.mythos.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.text.*
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mythos.app.ui.theme.MythosColors
import com.mythos.app.ui.theme.MythosMessage

@Composable
fun MessageBubble(
    message: MythosMessage,
    modifier: Modifier = Modifier,
) {
    val isUser = message.role == "user"
    val borderColor = if (isUser) MythosColors.Accent else MythosColors.Success
    val roleName = if (isUser) "You" else "Mythos"

    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp)
            .drawBehind {
                drawLine(
                    color = borderColor,
                    start = Offset(0f, 0f),
                    end = Offset(0f, size.height),
                    strokeWidth = 2.dp.toPx(),
                )
            }
            .padding(start = 12.dp),
    ) {
        Text(
            text = roleName,
            color = if (isUser) MythosColors.Accent2 else MythosColors.Success,
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
        )

        Spacer(modifier = Modifier.height(4.dp))

        // Parse and render content
        val parts = parseMessageContent(message.content)
        parts.forEach { part ->
            when (part) {
                is ContentPart.Code -> CodeBlockView(code = part.code, language = part.language)
                is ContentPart.Text -> {
                    if (part.text.isNotBlank()) {
                        Text(
                            text = part.text,
                            color = MythosColors.Text,
                            fontSize = 14.sp,
                            lineHeight = 20.sp,
                        )
                    }
                }
            }
        }

        if (message.reasoning != null) {
            Spacer(modifier = Modifier.height(6.dp))
            ThinkingBlock(reasoning = message.reasoning)
        }
    }
}

sealed class ContentPart {
    data class Text(val text: String) : ContentPart()
    data class Code(val language: String, val code: String) : ContentPart()
}

fun parseMessageContent(content: String): List<ContentPart> {
    val parts = mutableListOf<ContentPart>()
    val codeBlockRegex = Regex("```(\\w*)\\n?(.*?)```", RegexOption.DOT_MATCHES_ALL)
    var lastEnd = 0

    for (match in codeBlockRegex.findAll(content)) {
        if (match.range.first > lastEnd) {
            val textBefore = content.substring(lastEnd, match.range.first).trim()
            if (textBefore.isNotEmpty()) {
                parts.add(ContentPart.Text(textBefore))
            }
        }
        val lang = match.groupValues[1].ifEmpty { "text" }
        val code = match.groupValues[2].trimEnd('\n')
        parts.add(ContentPart.Code(lang, code))
        lastEnd = match.range.last + 1
    }

    if (lastEnd < content.length) {
        val remaining = content.substring(lastEnd).trim()
        if (remaining.isNotEmpty()) {
            parts.add(ContentPart.Text(remaining))
        }
    }

    if (parts.isEmpty()) {
        parts.add(ContentPart.Text(content))
    }

    return parts
}
