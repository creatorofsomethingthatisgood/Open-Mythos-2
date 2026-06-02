package com.mythos.app.engine

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emptyFlow

/**
 * Local inference engine via llama.cpp JNI.
 * Stub for v2 -- will call native llama.cpp functions when the NDK build is set up.
 */
class LocalEngine : InferenceEngine {

    override val isAvailable: Boolean = false
    override val name: String = "Local (Coming Soon)"

    override suspend fun chat(
        messages: List<Map<String, String>>,
        systemPrompt: String?,
        settings: Map<String, Any>,
    ): String {
        throw UnsupportedOperationException("Local inference not yet available. Use Cloud mode.")
    }

    override fun chatStream(
        messages: List<Map<String, String>>,
        systemPrompt: String?,
        settings: Map<String, Any>,
    ): Flow<String> = emptyFlow()

    override fun countTokens(text: String): Int {
        if (text.isBlank()) return 0
        return maxOf(1, text.length / 4)
    }
}
