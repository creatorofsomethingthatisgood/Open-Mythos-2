module engine

// Context budget: fit chat prompts into the model context window.

pub struct TokenCountable {
pub mut:
	count_tokens    fn (text string) int
	context_length  int
	format_chat_prompt fn (messages []ChatMessage, system_prompt string) string
}

// FitResult is the result of fitting chat context into the budget.
pub struct FitResult {
pub:
	messages     []ChatMessage
	system_prompt string
	token_count  int
}

// count_chat_prompt_tokens counts tokens in the formatted chat prompt.
pub fn count_chat_prompt_tokens(count_fn fn (string) int, format_fn fn ([]ChatMessage, string) string,
	messages []ChatMessage, system_prompt string) int {
	prompt := format_fn(messages, system_prompt)
	return count_fn(prompt)
}

// truncate_text shortens text to max_chars with a truncation suffix.
pub fn truncate_text(text string, max_chars int, suffix string) string {
	if text.len <= max_chars {
		return text
	}
	keep := max_chars - suffix.len
	if keep < 0 {
		keep = 0
	}
	return text[..keep] + suffix
}

// fit_chat_context shrinks history and/or system prompt so the request fits in n_ctx.
// Algorithm: 1) drop oldest turns, 2) shrink system prompt, 3) keep only latest message.
pub fn fit_chat_context(
	count_fn fn (text string) int
	format_fn fn (messages []ChatMessage, system_prompt string) string
	context_length int
	messages []ChatMessage
	system_prompt string
	reserve_tokens int
) FitResult {
	budget := if context_length - reserve_tokens > 512 { context_length - reserve_tokens } else { 512 }

	mut msgs := messages.clone()
	mut system := system_prompt

	mut used := count_chat_prompt_tokens(count_fn, format_fn, msgs, system)

	if used <= budget {
		return FitResult{msgs, system, used}
	}

	eprintln('Prompt ${used} tokens exceeds budget ${budget} (n_ctx=${context_length}); trimming...')

	// 1. Drop oldest conversation turns (user+assistant pairs)
	for used > budget && msgs.len >= 2 {
		if msgs.len <= 2 {
			break
		}
		msgs = msgs[2..]
		used = count_chat_prompt_tokens(count_fn, format_fn, msgs, system)
	}

	// 2. Shrink system/RAG block
	trunc_suffix := '\n\n[... truncated for context limit ...]'
	for used > budget && system.len > 2000 {
		system = truncate_text(system, int(f64(system.len) * 0.75), trunc_suffix)
		used = count_chat_prompt_tokens(count_fn, format_fn, msgs, system)
	}

	for used > budget && system.len > 500 {
		new_len := if system.len - 4000 > 500 { system.len - 4000 } else { 500 }
		system = truncate_text(system, new_len, trunc_suffix)
		used = count_chat_prompt_tokens(count_fn, format_fn, msgs, system)
	}

	// 3. Last resort: only latest user message
	if used > budget && msgs.len > 1 {
		msgs = msgs[msgs.len - 1..]
		used = count_chat_prompt_tokens(count_fn, format_fn, msgs, system)
	}

	if used > budget {
		eprintln('Prompt still ${used} tokens after trimming (budget ${budget}). Raise context_length or lower rag.top_k.')
	}

	return FitResult{msgs, system, used}
}
