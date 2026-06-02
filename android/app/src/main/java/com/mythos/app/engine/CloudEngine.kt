package com.mythos.app.engine

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.concurrent.TimeUnit

@Serializable
data class ChatMessage(val role: String, val content: String)

class CloudEngine(
    private var baseUrl: String,
    private var modelName: String,
    private var apiKey: String,
    private val defaultMaxTokens: Int = 4096,
    private val defaultTemperature: Double = 0.7,
    private val defaultTopP: Double = 0.9,
) : InferenceEngine {

    override val isAvailable: Boolean
        get() = apiKey.isNotBlank()

    override val name: String = "Cloud"

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(180, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    override suspend fun chat(
        messages: List<Map<String, String>>,
        systemPrompt: String?,
        settings: Map<String, Any>,
    ): String {
        val allMessages = mutableListOf<Map<String, String>>()
        if (systemPrompt != null) {
            allMessages.add(mapOf("role" to "system", "content" to systemPrompt))
        }
        allMessages.addAll(messages)

        val body = buildJsonObject {
            put("model", modelName)
            put("messages", JsonArray(allMessages.map { msg ->
                buildJsonObject {
                    put("role", msg["role"] ?: "user")
                    put("content", msg["content"] ?: "")
                }
            }))
            put("max_tokens", (settings["maxTokens"] as? Number)?.toInt() ?: defaultMaxTokens)
            put("temperature", (settings["temperature"] as? Number)?.toDouble() ?: defaultTemperature)
            put("top_p", (settings["topP"] as? Number)?.toDouble() ?: defaultTopP)
            put("stream", false)
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/chat/completions")
            .addHeader("Authorization", "Bearer $apiKey")
            .addHeader("Content-Type", "application/json")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()

        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            val errBody = response.body?.string() ?: "Unknown error"
            throw Exception("API error ${response.code}: $errBody")
        }

        val responseBody = response.body?.string() ?: throw Exception("Empty response")
        val jsonResp = json.parseToJsonElement(responseBody).jsonObject
        return jsonResp["choices"]?.jsonArray?.firstOrNull()
            ?.jsonObject?.get("message")?.jsonObject?.get("content")
            ?.jsonPrimitive?.content?.trim() ?: ""
    }

    override fun chatStream(
        messages: List<Map<String, String>>,
        systemPrompt: String?,
        settings: Map<String, Any>,
    ): Flow<String> = flow {
        val allMessages = mutableListOf<Map<String, String>>()
        if (systemPrompt != null) {
            allMessages.add(mapOf("role" to "system", "content" to systemPrompt))
        }
        allMessages.addAll(messages)

        val body = buildJsonObject {
            put("model", modelName)
            put("messages", JsonArray(allMessages.map { msg ->
                buildJsonObject {
                    put("role", msg["role"] ?: "user")
                    put("content", msg["content"] ?: "")
                }
            }))
            put("max_tokens", (settings["maxTokens"] as? Number)?.toInt() ?: defaultMaxTokens)
            put("temperature", (settings["temperature"] as? Number)?.toDouble() ?: defaultTemperature)
            put("top_p", (settings["topP"] as? Number)?.toDouble() ?: defaultTopP)
            put("stream", true)
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/chat/completions")
            .addHeader("Authorization", "Bearer $apiKey")
            .addHeader("Content-Type", "application/json")
            .addHeader("Accept", "text/event-stream")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()

        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            val errBody = response.body?.string() ?: "Unknown error"
            throw Exception("API error ${response.code}: $errBody")
        }

        val reader = BufferedReader(InputStreamReader(response.body?.byteStream() ?: return@flow))
        try {
            var line: String?
            while (reader.readLine().also { line = it } != null) {
                val currentLine = line ?: continue
                if (currentLine.isBlank() || !currentLine.startsWith("data: ")) continue
                val payload = currentLine.substring(6).trim()
                if (payload == "[DONE]") break
                try {
                    val chunk = json.parseToJsonElement(payload).jsonObject
                    val delta = chunk["choices"]?.jsonArray?.firstOrNull()
                        ?.jsonObject?.get("delta")?.jsonObject
                    val content = delta?.get("content")?.jsonPrimitive?.content ?: ""
                    if (content.isNotEmpty()) {
                        emit(content)
                    }
                } catch (e: Exception) {
                    // Skip malformed chunks
                    continue
                }
            }
        } finally {
            reader.close()
            response.close()
        }
    }.flowOn(Dispatchers.IO)

    override fun countTokens(text: String): Int {
        if (text.isBlank()) return 0
        return maxOf(1, text.length / 4)
    }

    fun updateConfig(baseUrl: String, modelName: String, apiKey: String) {
        this.baseUrl = baseUrl
        this.modelName = modelName
        this.apiKey = apiKey
    }
}
