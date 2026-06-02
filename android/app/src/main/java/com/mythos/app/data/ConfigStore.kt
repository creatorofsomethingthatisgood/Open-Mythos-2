package com.mythos.app.data

import android.content.Context
import android.content.SharedPreferences

/**
 * Persists user settings via SharedPreferences.
 * Mirrors config.yaml generation + cloud sections.
 */
class ConfigStore(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences("mythos_config", Context.MODE_PRIVATE)

    // Cloud settings
    var apiKey: String
        get() = prefs.getString("api_key", "") ?: ""
        set(value) = prefs.edit().putString("api_key", value).apply()

    var baseUrl: String
        get() = prefs.getString("base_url", "https://integrate.api.nvidia.com/v1")
            ?: "https://integrate.api.nvidia.com/v1"
        set(value) = prefs.edit().putString("base_url", value).apply()

    var modelName: String
        get() = prefs.getString("model_name", "meta/llama-3.3-70b-instruct")
            ?: "meta/llama-3.3-70b-instruct"
        set(value) = prefs.edit().putString("model_name", value).apply()

    var providerName: String
        get() = prefs.getString("provider_name", "NVIDIA") ?: "NVIDIA"
        set(value) = prefs.edit().putString("provider_name", value).apply()

    // Generation params
    var temperature: Float
        get() = prefs.getFloat("temperature", 0.7f)
        set(value) = prefs.edit().putFloat("temperature", value).apply()

    var topP: Float
        get() = prefs.getFloat("top_p", 0.9f)
        set(value) = prefs.edit().putFloat("top_p", value).apply()

    var topK: Int
        get() = prefs.getInt("top_k", 40)
        set(value) = prefs.edit().putInt("top_k", value).apply()

    var maxTokens: Int
        get() = prefs.getInt("max_tokens", 2048)
        set(value) = prefs.edit().putInt("max_tokens", value).apply()

    var repeatPenalty: Float
        get() = prefs.getFloat("repeat_penalty", 1.1f)
        set(value) = prefs.edit().putFloat("repeat_penalty", value).apply()

    // Feature toggles
    var thinkingEnabled: Boolean
        get() = prefs.getBoolean("thinking_enabled", true)
        set(value) = prefs.edit().putBoolean("thinking_enabled", value).apply()

    var reflectionEnabled: Boolean
        get() = prefs.getBoolean("reflection_enabled", false)
        set(value) = prefs.edit().putBoolean("reflection_enabled", value).apply()

    // Mode
    var codingMode: String
        get() = prefs.getString("coding_mode", "chat") ?: "chat"
        set(value) = prefs.edit().putString("coding_mode", value).apply()

    // Current session
    var currentSessionId: String
        get() = prefs.getString("current_session_id", "") ?: ""
        set(value) = prefs.edit().putString("current_session_id", value).apply()
}
