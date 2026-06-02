package com.mythos.app.data

import android.content.Context
import java.io.InputStream

/**
 * Loads prompt templates from assets/prompts/.
 * Mirrors engine/prompt_manager.py.
 */
class PromptStore(private val context: Context) {

    private val cache = mutableMapOf<String, String>()

    fun loadPrompt(name: String): String {
        cache[name]?.let { return it }

        val filename = if (name.startsWith("prompts/")) name else "prompts/$name"
        val assetPath = if (filename.endsWith(".txt")) filename else "$filename.txt"

        val stream: InputStream = context.assets.open(assetPath)
        val text = stream.bufferedReader().use { it.readText() }
        cache[name] = text
        return text
    }

    fun listTemplates(): List<String> {
        return context.assets.list("prompts")?.toList() ?: emptyList()
    }

    companion object {
        val MODE_PROMPTS = mapOf(
            "code" to "prompts/coding.txt",
            "review" to "prompts/code_review.txt",
            "debug" to "prompts/debugging.txt",
            "architect" to "prompts/analytical.txt",
            "chat" to "prompts/default.txt",
            "security" to "prompts/security_audit.txt",
        )
    }
}
