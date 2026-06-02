package com.mythos.app.engine

data class ProviderPreset(
    val name: String,
    val baseUrl: String,
    val defaultModel: String,
)

object ProviderPresets {
    val OPENAI = ProviderPreset(
        name = "OpenAI",
        baseUrl = "https://api.openai.com/v1",
        defaultModel = "gpt-4o-mini",
    )
    val NVIDIA = ProviderPreset(
        name = "NVIDIA",
        baseUrl = "https://integrate.api.nvidia.com/v1",
        defaultModel = "meta/llama-3.3-70b-instruct",
    )
    val TOGETHER = ProviderPreset(
        name = "Together",
        baseUrl = "https://api.together.xyz/v1",
        defaultModel = "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    )
    val GROQ = ProviderPreset(
        name = "Groq",
        baseUrl = "https://api.groq.com/openai/v1",
        defaultModel = "llama-3.3-70b-versatile",
    )

    val ALL = listOf(OPENAI, NVIDIA, TOGETHER, GROQ)

    fun findByName(name: String): ProviderPreset? = ALL.find { it.name.equals(name, ignoreCase = true) }
}
