package com.mythos.app.ui.theme

data class MythosMessage(
    val id: Long = 0,
    val role: String, // "user", "assistant", "system"
    val content: String,
    val timestamp: Long = System.currentTimeMillis(),
    val reasoning: String? = null,
)

enum class CodingMode(val key: String, val label: String, val icon: String, val promptFile: String, val defaultTemp: Float) {
    CODE("code", "Code", "</>", "prompts/coding.txt", 0.2f),
    REVIEW("review", "Review", "R", "prompts/code_review.txt", 0.3f),
    DEBUG("debug", "Debug", "B", "prompts/debugging.txt", 0.3f),
    ARCHITECT("architect", "Architect", "A", "prompts/analytical.txt", 0.5f),
    CHAT("chat", "Chat", "C", "prompts/default.txt", 0.7f),
    SECURITY("security", "Security", "S", "prompts/security_audit.txt", 0.2f);

    companion object {
        fun fromKey(key: String): CodingMode = entries.find { it.key == key } ?: CHAT
    }
}

data class ModeConfig(
    val key: String,
    val label: String,
    val icon: String,
    val promptFile: String,
    val temp: Float,
)

val MODE_CONFIG = listOf(
    ModeConfig("code", "Code", "</>", "prompts/coding.txt", 0.2f),
    ModeConfig("review", "Review", "R", "prompts/code_review.txt", 0.3f),
    ModeConfig("debug", "Debug", "B", "prompts/debugging.txt", 0.3f),
    ModeConfig("architect", "Architect", "A", "prompts/analytical.txt", 0.5f),
    ModeConfig("chat", "Chat", "C", "prompts/default.txt", 0.7f),
    ModeConfig("security", "Security", "S", "prompts/security_audit.txt", 0.2f),
)

data class SlashCommand(
    val name: String,
    val description: String,
    val usage: String,
    val aliases: List<String> = emptyList(),
    val args: String? = null,
)

val SLASH_COMMANDS = listOf(
    SlashCommand("help", "Show all available commands", "/help"),
    SlashCommand("clear", "Clear conversation history", "/clear"),
    SlashCommand("save", "Save current conversation", "/save"),
    SlashCommand("export", "Export conversation as text", "/export"),
    SlashCommand("markdown", "Export conversation as Markdown", "/markdown"),
    SlashCommand("copy", "Copy last response to clipboard", "/copy"),
    SlashCommand("redo", "Regenerate the last assistant response", "/redo"),
    SlashCommand("mode", "Switch coding mode", "/mode <mode>", args = "<mode>"),
    SlashCommand("persona", "Switch persona", "/persona <name>", args = "<name>"),
    SlashCommand("system", "Change system prompt template", "/system <template>", args = "<template>"),
    SlashCommand("temp", "Set temperature (0.0-2.0)", "/temp <value>", args = "<0.0-2.0>"),
    SlashCommand("topp", "Set top-p (0.0-1.0)", "/topp <value>", args = "<0.0-1.0>"),
    SlashCommand("think", "Toggle thinking display", "/think <on|off>", aliases = listOf("thinking"), args = "<on|off>"),
    SlashCommand("reflect", "Toggle self-reflection", "/reflect <on|off>", args = "<on|off>"),
    SlashCommand("config", "Show current configuration", "/config"),
    SlashCommand("version", "Show Mythos version and model info", "/version"),
)

fun matchCommands(input: String): List<SlashCommand> {
    if (!input.startsWith("/")) return emptyList()
    val query = input.drop(1).lowercase().split("\\s".toRegex()).firstOrNull() ?: ""
    if (query.isEmpty()) return SLASH_COMMANDS
    return SLASH_COMMANDS.filter { c ->
        c.name.startsWith(query) || c.aliases.any { it.startsWith(query) }
    }
}
