package com.mythos.app.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mythos.app.ui.theme.MythosColors

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ModelScreen(
    currentEngine: String,
    currentModel: String,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Models", color = MythosColors.Text) },
                navigationIcon = {
                    TextButton(onClick = onBack) {
                        Text("Back", color = MythosColors.Accent2)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MythosColors.Surface,
                ),
            )
        },
        containerColor = MythosColors.Bg,
        modifier = modifier,
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // Active engine
            Surface(
                shape = RoundedCornerShape(8.dp),
                color = MythosColors.Surface,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Active Engine", color = MythosColors.Text3, fontSize = 12.sp)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        currentEngine,
                        color = MythosColors.Accent2,
                        fontSize = 18.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        currentModel,
                        color = MythosColors.Text2,
                        fontSize = 13.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }

            // Local models (coming soon)
            Surface(
                shape = RoundedCornerShape(8.dp),
                color = MythosColors.Surface,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Local Models", color = MythosColors.Text, fontSize = 16.sp)
                    Spacer(modifier = Modifier.height(8.dp))
                    Text("Coming Soon", color = MythosColors.Text3, fontSize = 14.sp)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        "Local GGUF inference via llama.cpp JNI will be available in a future update. Planned models: Qwen2-1.5B Q4, Phi-3-Mini Q4, Qwen2.5-7B Q4.",
                        color = MythosColors.Text3,
                        fontSize = 12.sp,
                    )
                }
            }
        }
    }
}
