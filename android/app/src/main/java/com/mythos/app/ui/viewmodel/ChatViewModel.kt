package com.mythos.app.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.mythos.app.data.ConfigStore
import com.mythos.app.data.ConversationStore
import com.mythos.app.data.MessageEntity
import com.mythos.app.engine.CloudEngine
import com.mythos.app.engine.InferenceEngine
import com.mythos.app.engine.LocalEngine
import com.mythos.app.engine.ProviderPresets
import com.mythos.app.data.PromptStore
import com.mythos.app.ui.theme.CodingMode
import com.mythos.app.ui.theme.MythosMessage
import com.mythos.app.ui.theme.SlashCommand
import com.mythos.app.ui.theme.matchCommands
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.util.UUID

class ChatViewModel(application: Application) : AndroidViewModel(application) {

    private val config = ConfigStore(application)
    private val promptStore = PromptStore(application)

    private val cloudEngine = CloudEngine(
        baseUrl = config.baseUrl,
        modelName = config.modelName,
        apiKey = config.apiKey,
    )
    private val localEngine = LocalEngine()

    private val engine: InferenceEngine
        get() = if (cloudEngine.isAvailable) cloudEngine else localEngine

    private var conversationStore: ConversationStore? = null

    // --- State ---

    private val _messages = MutableStateFlow<List<MythosMessage>>(emptyList())
    val messages: StateFlow<List<MythosMessage>> = _messages.asStateFlow()

    private val _isGenerating = MutableStateFlow(false)
    val isGenerating: StateFlow<Boolean> = _isGenerating.asStateFlow()

    private val _currentMode = MutableStateFlow(CodingMode.fromKey(config.codingMode))
    val currentMode: StateFlow<CodingMode> = _currentMode.asStateFlow()

    private val _streamingText = MutableStateFlow("")
    val streamingText: StateFlow<String> = _streamingText.asStateFlow()

    private val _tokenCount = MutableStateFlow(0)
    val tokenCount: StateFlow<Int> = _tokenCount.asStateFlow()

    private val _engineName = MutableStateFlow("Cloud")
    val engineName: StateFlow<String> = _engineName.asStateFlow()

    private val _showCommands = MutableStateFlow(false)
    val showCommands: StateFlow<Boolean> = _showCommands.asStateFlow()

    private val _matchedCommands = MutableStateFlow<List<SlashCommand>>(emptyList())
    val matchedCommands: StateFlow<List<SlashCommand>> = _matchedCommands.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private var sessionId: String = config.currentSessionId.ifEmpty {
        UUID.randomUUID().toString()
    }

    init {
        config.currentSessionId = sessionId
        updateEngineConfig()
        _engineName.value = if (cloudEngine.isAvailable) "Cloud" else localEngine.name
    }

    fun setConversationStore(store: ConversationStore) {
        conversationStore = store
        loadSession()
    }

    private fun loadSession() {
        viewModelScope.launch {
            conversationStore?.getMessageList(sessionId)?.let { entities ->
                _messages.value = entities.map { it.toMythosMessage() }
            }
        }
    }

    fun send(text: String) {
        if (text.startsWith("/")) {
            handleSlashCommand(text)
            return
        }

        val userMsg = MythosMessage(role = "user", content = text)
        addMessage(userMsg)

        viewModelScope.launch {
            _isGenerating.value = true
            _error.value = null
            _streamingText.value = ""

            try {
                val systemPrompt = loadSystemPrompt()
                val chatMessages = _messages.value.map {
                    mapOf("role" to it.role, "content" to it.content)
                }
                val settings = mapOf(
                    "temperature" to getTemperatureForMode(),
                    "topP" to config.topP.toDouble(),
                    "maxTokens" to config.maxTokens,
                )

                val fullResponse = StringBuilder()
                engine.chatStream(chatMessages, systemPrompt, settings).collect { token ->
                    fullResponse.append(token)
                    _streamingText.value = fullResponse.toString()
                }

                val responseText = fullResponse.toString().trim()
                if (responseText.isNotEmpty()) {
                    val (thinking, content) = extractThinking(responseText)
                    val assistantMsg = MythosMessage(
                        role = "assistant",
                        content = content,
                        reasoning = thinking,
                    )
                    addMessage(assistantMsg)
                    _tokenCount.value += engine.countTokens(content)
                }
            } catch (e: Exception) {
                _error.value = e.message ?: "Error generating response"
            } finally {
                _isGenerating.value = false
                _streamingText.value = ""
            }
        }
    }

    private fun addMessage(msg: MythosMessage) {
        _messages.value = _messages.value + msg
        viewModelScope.launch {
            conversationStore?.addMessage(sessionId, msg.role, msg.content, msg.reasoning)
        }
    }

    private fun handleSlashCommand(input: String) {
        val parts = input.drop(1).trim().split("\\s+".toRegex(), limit = 2)
        val name = parts.firstOrNull() ?: ""
        val args = parts.getOrElse(1) { "" }

        when (name) {
            "clear" -> {
                _messages.value = emptyList()
                viewModelScope.launch {
                    conversationStore?.clearSession(sessionId)
                }
            }
            "mode" -> {
                val mode = CodingMode.fromKey(args)
                _currentMode.value = mode
                config.codingMode = mode.key
            }
            "temp" -> {
                args.toFloatOrNull()?.let { config.temperature = it }
            }
            "topp" -> {
                args.toFloatOrNull()?.let { config.topP = it }
            }
            "think", "thinking" -> {
                config.thinkingEnabled = when (args) {
                    "on" -> true
                    "off" -> false
                    else -> !config.thinkingEnabled
                }
            }
            "config" -> {
                val info = "Mode: ${_currentMode.value.label}\n" +
                    "Temp: ${config.temperature}\n" +
                    "TopP: ${config.topP}\n" +
                    "TopK: ${config.topK}\n" +
                    "MaxTokens: ${config.maxTokens}\n" +
                    "Thinking: ${config.thinkingEnabled}\n" +
                    "Engine: ${engine.name}\n" +
                    "Model: ${config.modelName}"
                addMessage(MythosMessage(role = "assistant", content = info))
            }
            "version" -> {
                addMessage(MythosMessage(role = "assistant", content = "Mythos 2.0.5 - Android"))
            }
            "export", "markdown" -> {
                viewModelScope.launch {
                    conversationStore?.exportAsMarkdown(sessionId)?.let {
                        addMessage(MythosMessage(
                            role = "assistant",
                            content = "Exported ${_messages.value.size} messages.",
                        ))
                    }
                }
            }
        }

        _showCommands.value = false
        _matchedCommands.value = emptyList()
    }

    fun handleCommand(input: String) {
        handleSlashCommand(input)
    }

    fun onInputChange(text: String) {
        if (text.startsWith("/")) {
            _matchedCommands.value = matchCommands(text)
            _showCommands.value = _matchedCommands.value.isNotEmpty()
        } else {
            _showCommands.value = false
            _matchedCommands.value = emptyList()
        }
    }

    fun selectCommand(cmd: SlashCommand) {
        handleSlashCommand("/${cmd.name}")
    }

    fun switchMode(mode: CodingMode) {
        _currentMode.value = mode
        config.codingMode = mode.key
    }

    fun switchMode(modeKey: String) {
        val mode = CodingMode.fromKey(modeKey)
        switchMode(mode)
    }

    fun updateCloudConfig(baseUrl: String, modelName: String, apiKey: String) {
        cloudEngine.updateConfig(baseUrl, modelName, apiKey)
        config.baseUrl = baseUrl
        config.modelName = modelName
        config.apiKey = apiKey
        _engineName.value = if (cloudEngine.isAvailable) "Cloud" else localEngine.name
    }

    fun applyProviderPreset(presetName: String) {
        ProviderPresets.findByName(presetName)?.let { preset ->
            updateCloudConfig(preset.baseUrl, preset.defaultModel, config.apiKey)
        }
    }

    private fun loadSystemPrompt(): String {
        val modePromptFile = CodingMode.fromKey(config.codingMode).promptFile
        return try {
            promptStore.loadPrompt(modePromptFile)
        } catch (e: Exception) {
            "You are Mythos, an advanced AI assistant."
        }
    }

    private fun getTemperatureForMode(): Double {
        return _currentMode.value.defaultTemp.toDouble()
    }

    private fun updateEngineConfig() {
        cloudEngine.updateConfig(config.baseUrl, config.modelName, config.apiKey)
    }

    private fun extractThinking(response: String): Pair<String?, String> {
        val thinkRegex = Regex(
            "(?:\uD83E\uDD16|\\[THINKING\\])(.*?)(?:\uD83E\uDD16|\\[/THINKING\\])",
            RegexOption.DOT_MATCHES_ALL,
        )
        val match = thinkRegex.find(response)
        return if (match != null) {
            val thinking = match.groupValues[1].trim()
            val content = response.replace(match.value, "").trim()
            thinking to content
        } else {
            null to response
        }
    }

    fun clearChat() {
        sessionId = UUID.randomUUID().toString()
        config.currentSessionId = sessionId
        _messages.value = emptyList()
        _tokenCount.value = 0
        viewModelScope.launch {
            conversationStore?.createSession(sessionId, _currentMode.value.key)
        }
    }
}

private fun MessageEntity.toMythosMessage() = MythosMessage(
    id = id,
    role = role,
    content = content,
    timestamp = timestamp,
    reasoning = reasoning,
)
