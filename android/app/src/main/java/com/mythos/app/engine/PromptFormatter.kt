package com.mythos.app.engine

/**
 * Format chat messages into a raw prompt string for local inference.
 * Ported from engine/inference.py format_chat_prompt().
 * Not needed for cloud mode (cloud uses the messages API directly),
 * but required for local GGUF inference in v2.
 */
object PromptFormatter {

    fun format(modelName: String, messages: List<Map<String, String>>, systemPrompt: String?): String {
        return when {
            modelName.contains("qwen", ignoreCase = true) -> formatQwen(messages, systemPrompt)
            modelName.contains("mistral", ignoreCase = true) -> formatMistral(messages, systemPrompt)
            modelName.contains("llama", ignoreCase = true) -> formatLlama3(messages, systemPrompt)
            else -> formatChatML(messages, systemPrompt)
        }
    }

    /** ChatML format (Qwen, generic) */
    fun formatChatML(messages: List<Map<String, String>>, systemPrompt: String?): String {
        val sb = StringBuilder()
        if (systemPrompt != null) {
            sb.append("<|im_start|>system\n$systemPrompt<|im_end|>\n")
        }
        for (msg in messages) {
            val role = msg["role"] ?: "user"
            val content = msg["content"] ?: ""
            sb.append("<|im_start|>$role\n$content<|im_end|>\n")
        }
        sb.append("<|im_start|>assistant\n")
        return sb.toString()
    }

    /** Qwen format (same as ChatML) */
    fun formatQwen(messages: List<Map<String, String>>, systemPrompt: String?): String =
        formatChatML(messages, systemPrompt)

    /** Mistral instruct format */
    fun formatMistral(messages: List<Map<String, String>>, systemPrompt: String?): String {
        val sb = StringBuilder()
        if (systemPrompt != null) {
            sb.append("<s>[INST] $systemPrompt\n\n")
        } else {
            sb.append("<s>[INST] ")
        }
        messages.forEachIndexed { i, msg ->
            if (msg["role"] == "user") {
                if (i > 0) {
                    sb.append("[INST] ${msg["content"]} [/INST]")
                } else {
                    sb.append("${msg["content"]} [/INST]")
                }
            } else if (msg["role"] == "assistant") {
                sb.append(" ${msg["content"]}</s>")
            }
        }
        return sb.toString()
    }

    /** Llama 3 format */
    fun formatLlama3(messages: List<Map<String, String>>, systemPrompt: String?): String {
        val sb = StringBuilder("<|begin_of_text|>")
        if (systemPrompt != null) {
            sb.append("<|start_header_id|>system<|end_header_id|>\n\n$systemPrompt<|eot_id|>")
        }
        for (msg in messages) {
            val role = msg["role"] ?: "user"
            val content = msg["content"] ?: ""
            sb.append("<|start_header_id|>$role<|end_header_id|>\n\n$content<|eot_id|>")
        }
        sb.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
        return sb.toString()
    }
}
