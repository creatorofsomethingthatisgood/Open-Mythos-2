package com.mythos.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.mythos.app.ui.theme.MythosTheme
import com.mythos.app.ui.screens.ChatScreen
import com.mythos.app.ui.viewmodel.ChatViewModel
import androidx.lifecycle.viewmodel.compose.viewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MythosTheme {
                MythosAppContent()
            }
        }
    }
}

@Composable
private fun MythosAppContent() {
    val app = androidx.compose.ui.platform.LocalContext.current.applicationContext as MythosApp
    val viewModel: ChatViewModel = viewModel(factory = ChatViewModelFactory(app))

    // Wire up ConversationStore once
    androidx.compose.runtime.LaunchedEffect(Unit) {
        viewModel.setConversationStore(app.conversationStore)
    }

    Surface(modifier = Modifier.fillMaxSize()) {
        ChatScreen(viewModel = viewModel)
    }
}
