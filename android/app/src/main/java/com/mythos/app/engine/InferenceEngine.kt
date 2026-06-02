package com.mythos.app.engine

import kotlinx.coroutines.flow.Flow

/**
 * Abstract inference backend. Cloud and local engines both implement this.
 */
interface InferenceEngine {
    suspend fun chat(messages: List<Map<String, String>>, systemPrompt: String?, settings: Map<String, Any>): String
    fun chatStream(messages: List<Map<String, String>>, systemPrompt: String?, settings: Map<String, Any>): Flow<String>
    fun countTokens(text: String): Int
    val isAvailable: Boolean
    val name: String
}
