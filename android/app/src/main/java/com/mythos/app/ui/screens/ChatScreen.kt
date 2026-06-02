package com.mythos.app.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.mythos.app.ui.components.*
import com.mythos.app.ui.theme.MythosColors
import com.mythos.app.ui.theme.MythosMessage
import com.mythos.app.ui.viewmodel.ChatViewModel

@Composable
fun ChatScreen(
    viewModel: ChatViewModel = viewModel(),
    modifier: Modifier = Modifier,
) {
    val messages by viewModel.messages.collectAsState()
    val isGenerating by viewModel.isGenerating.collectAsState()
    val currentMode by viewModel.currentMode.collectAsState()
    val streamingText by viewModel.streamingText.collectAsState()
    val tokenCount by viewModel.tokenCount.collectAsState()
    val engineName by viewModel.engineName.collectAsState()
    val showCommands by viewModel.showCommands.collectAsState()
    val matchedCommands by viewModel.matchedCommands.collectAsState()
    val error by viewModel.error.collectAsState()

    val listState = rememberLazyListState()

    LaunchedEffect(messages.size, streamingText) {
        if (messages.isNotEmpty() || streamingText.isNotEmpty()) {
            listState.animateScrollToItem(listState.layoutInfo.totalItemsCount - 1)
        }
    }

    Scaffold(
        containerColor = MythosColors.Bg,
        topBar = {
            ModeBar(
                currentMode = currentMode,
                onModeChange = { viewModel.switchMode(it.key) },
            )
        },
        bottomBar = {
            Column {
                if (error != null) {
                    Surface(
                        color = MythosColors.Error.copy(alpha = 0.15f),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(
                            text = error!!,
                            color = MythosColors.Error,
                            fontSize = 12.sp,
                            fontFamily = FontFamily.Monospace,
                            modifier = Modifier.padding(12.dp),
                        )
                    }
                }

                if (showCommands && matchedCommands.isNotEmpty()) {
                    CommandSheet(
                        commands = matchedCommands,
                        onSelect = { viewModel.selectCommand(it) },
                    )
                }

                StatusBar(
                    mode = currentMode,
                    engineName = engineName,
                    tokenCount = tokenCount,
                    isGenerating = isGenerating,
                )

                InputBar(
                    onSend = { viewModel.send(it) },
                    isGenerating = isGenerating,
                )
            }
        },
    ) { padding ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            if (messages.isEmpty() && streamingText.isEmpty()) {
                QuickActions(onAction = { viewModel.send(it) })
                Spacer(modifier = Modifier.height(24.dp))
                Text(
                    "Start a conversation or use a quick action.",
                    color = MythosColors.Text3,
                    fontSize = 14.sp,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 24.dp),
                )
            }

            LazyColumn(
                state = listState,
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                items(messages) { msg ->
                    MessageBubble(message = msg)
                }

                if (streamingText.isNotEmpty()) {
                    item {
                        MessageBubble(
                            message = MythosMessage(role = "assistant", content = streamingText),
                        )
                    }
                }
            }
        }
    }
}
