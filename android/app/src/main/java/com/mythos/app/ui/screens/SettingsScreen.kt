package com.mythos.app.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mythos.app.engine.ProviderPresets
import com.mythos.app.ui.theme.MythosColors

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    apiKey: String,
    baseUrl: String,
    modelName: String,
    temperature: Float,
    topP: Float,
    maxTokens: Int,
    thinkingEnabled: Boolean,
    onSave: (apiKey: String, baseUrl: String, modelName: String, temp: Float, topP: Float, maxTokens: Int, thinking: Boolean) -> Unit,
    onProviderPreset: (String) -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var apiKeyState by remember { mutableStateOf(apiKey) }
    var baseUrlState by remember { mutableStateOf(baseUrl) }
    var modelNameState by remember { mutableStateOf(modelName) }
    var tempState by remember { mutableStateOf(temperature) }
    var topPState by remember { mutableStateOf(topP) }
    var maxTokensState by remember { mutableStateOf(maxTokens) }
    var thinkingState by remember { mutableStateOf(thinkingEnabled) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings", color = MythosColors.Text) },
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
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // Cloud API section
            SectionHeader("Cloud API")

            OutlinedTextField(
                value = baseUrlState,
                onValueChange = { baseUrlState = it },
                label = { Text("Base URL") },
                modifier = Modifier.fillMaxWidth(),
                colors = mythosTextFieldColors(),
                shape = RoundedCornerShape(8.dp),
            )

            OutlinedTextField(
                value = modelNameState,
                onValueChange = { modelNameState = it },
                label = { Text("Model") },
                modifier = Modifier.fillMaxWidth(),
                colors = mythosTextFieldColors(),
                shape = RoundedCornerShape(8.dp),
            )

            OutlinedTextField(
                value = apiKeyState,
                onValueChange = { apiKeyState = it },
                label = { Text("API Key") },
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth(),
                colors = mythosTextFieldColors(),
                shape = RoundedCornerShape(8.dp),
            )

            // Provider presets
            SectionHeader("Provider Presets")

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                ProviderPresets.ALL.forEach { preset ->
                    OutlinedButton(
                        onClick = { onProviderPreset(preset.name) },
                        shape = RoundedCornerShape(6.dp),
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = MythosColors.Accent2,
                        ),
                        border = ButtonDefaults.outlinedButtonBorder(enabled = true),
                        modifier = Modifier.weight(1f),
                    ) {
                        Text(preset.name, fontSize = 12.sp)
                    }
                }
            }

            // Generation params
            SectionHeader("Generation")

            ParamSlider("Temperature", tempState, 0f..2f) { tempState = it }
            ParamSlider("Top P", topPState, 0f..1f) { topPState = it }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("Max Tokens", color = MythosColors.Text2, fontSize = 13.sp)
                Text(
                    "$maxTokensState",
                    color = MythosColors.Accent2,
                    fontSize = 13.sp,
                    fontFamily = FontFamily.Monospace,
                )
            }

            Slider(
                value = maxTokensState.toFloat(),
                onValueChange = { maxTokensState = it.toInt() },
                valueRange = 128f..8192f,
                colors = SliderDefaults.colors(
                    thumbColor = MythosColors.Accent,
                    activeTrackColor = MythosColors.Accent,
                ),
            )

            // Toggles
            SectionHeader("Features")

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("Thinking Mode", color = MythosColors.Text2, fontSize = 14.sp)
                Switch(
                    checked = thinkingState,
                    onCheckedChange = { thinkingState = it },
                    colors = SwitchDefaults.colors(checkedTrackColor = MythosColors.Accent),
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Save button
            Button(
                onClick = {
                    onSave(
                        apiKeyState, baseUrlState, modelNameState,
                        tempState, topPState, maxTokensState, thinkingState,
                    )
                    onBack()
                },
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(8.dp),
                colors = ButtonDefaults.buttonColors(containerColor = MythosColors.Accent),
            ) {
                Text("Save Settings", color = MythosColors.Text)
            }
        }
    }
}

@Composable
private fun SectionHeader(text: String) {
    Text(
        text = text,
        color = MythosColors.Text,
        fontSize = 16.sp,
        modifier = Modifier.padding(top = 8.dp),
    )
}

@Composable
private fun ParamSlider(
    label: String,
    value: Float,
    range: ClosedFloatingPointRange<Float>,
    onChange: (Float) -> Unit,
) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(label, color = MythosColors.Text2, fontSize = 13.sp)
            Text(
                String.format("%.2f", value),
                color = MythosColors.Accent2,
                fontSize = 13.sp,
                fontFamily = FontFamily.Monospace,
            )
        }
        Slider(
            value = value,
            onValueChange = onChange,
            valueRange = range,
            colors = SliderDefaults.colors(
                thumbColor = MythosColors.Accent,
                activeTrackColor = MythosColors.Accent,
            ),
        )
    }
}

@Composable
private fun mythosTextFieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = MythosColors.Accent,
    unfocusedBorderColor = MythosColors.Border,
    focusedLabelColor = MythosColors.Accent2,
    unfocusedLabelColor = MythosColors.Text3,
    focusedTextColor = MythosColors.Text,
    unfocusedTextColor = MythosColors.Text,
    cursorColor = MythosColors.Accent2,
)
