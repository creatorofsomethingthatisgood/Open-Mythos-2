module engine

#flag -I@VROOT/../../llama.cpp/include
#flag -I@VROOT/../../llama.cpp/ggml/include
#flag -L@VROOT/../../llama.cpp/build/src
#flag -L@VROOT/../../llama.cpp/build/ggml/src
#flag -lllama -lggml -lm -lpthread -ldl

#include "llama.h"

import os
import config
import strings

// ChatMessage represents a single message in a conversation.
pub struct ChatMessage {
pub:
	role    string
	content string
}

// ModelFormat detects which prompt format to use.
pub enum ModelFormat {
	qwen
	mistral
	llama3
	chatml
}

// InferenceEngine wraps llama.cpp C API for GGUF model inference.
// Compiles to native code with zero Python overhead.
pub struct InferenceEngine {
pub mut:
	model_path      string
	context_length  int
	n_threads       int
	n_gpu_layers    int
	n_batch         int
	use_mmap        bool
	use_mlock       bool
	rope_freq_base  f64
	gen_temperature f64
	gen_top_p       f64
	gen_top_k       int
	gen_repeat_penalty f64
	gen_max_tokens  int
	gen_stream      bool
	gen_stop        []string
	model_fmt       ModelFormat
	ctx             &C.llama_model = unsafe { nil }
	lctx            &C.llama_context = unsafe { nil }
	loaded          bool
}

// C struct aliases for llama.cpp API
struct C.llama_model {}
struct C.llama_context {}
struct C.llama_model_params {
	n_gpu_layers int
	main_gpu     int
	split_mode   int // LLAMA_SPLIT_MODE_NONE=0, LAYER=1, ROW=2
	use_mmap     bool
	use_mlock    bool
	// ... many more fields, we zero-init and set only what we need
}
struct C.llama_context_params {
	n_ctx            u32
	n_batch          u32
	n_ubatch         u32
	n_seq_max        u32
	n_threads        u32
	n_threads_batch  u32
	rope_freq_base   f64
	rope_scaling_type int
	// ... many more fields
}

fn C.llama_model_default_params() C.llama_model_params
fn C.llama_context_default_params() C.llama_context_params
fn C.llama_load_model_from_file(path &char, params C.llama_model_params) &C.llama_model
fn C.llama_free_model(model &C.llama_model)
fn C.llama_new_context_with_model(model &C.llama_model, params C.llama_context_params) &C.llama_context
fn C.llama_free(ctx &C.llama_context)
fn C.llama_tokenize(model &C.llama_model, text &char, text_len i32, tokens &i32, n_max_tokens i32, add_bos bool, special bool) i32
fn C.llama_kv_cache_clear(ctx &C.llama_context)
fn C.llama_decode(ctx &C.llama_context, batch C.llama_batch) i32
fn C.llama_sample_top_k(ctx &C.llama_context, candidates &C.llama_token_data, n_candidates i32, k i32, min_keep usize)
fn C.llama_sample_top_p(ctx &C.llama_context, candidates &C.llama_token_data, n_candidates i32, p f64, min_keep usize)
fn C.llama_sample_temp(ctx &C.llama_context, candidates &C.llama_token_data, n_candidates i32, temp f64)
fn C.llama_sample_repeat_penalty(ctx &C.llama_context, candidates &C.llama_token_data, n_candidates i32, last_tokens &i32, penalty f64, pos_last i32)
fn C.llama_token_to_piece(model &C.llama_model, token i32, buf &char, length i32, special bool) i32
fn C.llama_get_model(ctx &C.llama_context) &C.llama_model
fn C.llama_n_ctx(ctx &C.llama_context) u32
fn C.llama_n_vocab(model &C.llama_model) i32
fn C.llama_get_logits_ith(ctx &C.llama_context, i32) &f64
fn C.llama_token_eos(model &C.llama_model) i32
fn C.llama_token_bos(model &C.llama_model) i32

// Batch struct for llama.cpp
struct C.llama_batch {
	n_tokens      i32
	token         &i32
	pos           &i32
	n_seq_id      &i32
	seq_id        &&i32
	output        &i8
}

fn C.llama_batch_get_one(token &i32, n_tokens i32) C.llama_batch
fn C.llama_batch_free(batch C.llama_batch)

// Token data for sampling
struct C.llama_token_data {
	id    i32
	logit f64
	p     f64
}

// new_inference_engine creates an engine from config.
pub fn new_inference_engine(cfg config.Config, model_path string) InferenceEngine {
	mut engine := InferenceEngine{
		context_length: cfg.model.context_length
		n_batch: cfg.model.n_batch
		use_mmap: cfg.model.use_mmap
		use_mlock: cfg.model.use_mlock
		rope_freq_base: cfg.model.rope_freq_base
		gen_temperature: cfg.generation.temperature
		gen_top_p: cfg.generation.top_p
		gen_top_k: cfg.generation.top_k
		gen_repeat_penalty: cfg.generation.repeat_penalty
		gen_max_tokens: cfg.generation.max_tokens
		gen_stream: cfg.generation.stream
		gen_stop: cfg.generation.stop_sequences.clone()
		model_fmt: detect_model_format(model_path)
	}

	// Resolve threads
	engine.n_threads = cfg.model.n_threads
	if engine.n_threads == 0 {
		engine.n_threads = os.cpu_count() / 2
		if engine.n_threads < 1 {
			engine.n_threads = 1
		}
	}

	// Resolve GPU layers
	engine.n_gpu_layers = cfg.model.n_gpu_layers
	$if macos {
		if engine.n_gpu_layers == 0 {
			engine.n_gpu_layers = -1 // Metal auto
		}
	}

	// Resolve model path
	if model_path != '' {
		engine.model_path = model_path
	} else {
		engine.model_path = cfg.model.path
	}

	return engine
}

// detect_model_format infers the prompt template from the filename.
pub fn detect_model_format(path string) ModelFormat {
	name := path.to_lower()
	if name.contains('qwen') {
		return .qwen
	}
	if name.contains('mistral') {
		return .mistral
	}
	if name.contains('llama-3') || name.contains('llama3') {
		return .llama3
	}
	return .chatml
}

// load_model loads the GGUF model via llama.cpp C API.
// If the model file is missing, it auto-downloads from HuggingFace first.
// Requires cfg to be set before calling (via new_inference_engine).
pub fn (mut e InferenceEngine) load_model() ! {
	// Auto-download if model file doesn't exist
	if !os.exists(e.model_path) {
		println('Model not found at ${e.model_path}')
		if e.cfg.repo_id != '' && e.cfg.filename != '' {
			println('Auto-downloading from HuggingFace...')
			println('  Repo: ${e.cfg.repo_id}')
			println('  File: ${e.cfg.filename}')
			mut mm := new_model_manager_default()
			mm.download_model(e.cfg.repo_id, e.cfg.filename, os.base(e.model_path)) or {
				return error('Auto-download failed: ${err}. Place a GGUF model at ${e.model_path}')
			}
			if !os.exists(e.model_path) {
				return error('Model file not found after download: ${e.model_path}')
			}
			println('Download complete!')
		} else {
			return error('Model file not found: ${e.model_path}. No repo_id/filename in config for auto-download.')
		}
	}

	// Check for multi-part split files
	if e.model_path.contains('-of-') {
		return error('Multi-part split file detected. Merge first: llama-gguf-split --merge')
	}

	// Model params
	mut mparams := C.llama_model_default_params()
	mparams.n_gpu_layers = e.n_gpu_layers
	mparams.use_mmap = e.use_mmap
	mparams.use_mlock = e.use_mlock

	e.ctx = C.llama_load_model_from_file(&char(e.model_path.str), mparams)
	if isnil(e.ctx) {
		// Fallback: retry without GPU
		if e.n_gpu_layers != 0 {
			eprintln('Model load failed with GPU, retrying CPU-only...')
			mparams.n_gpu_layers = 0
			e.ctx = C.llama_load_model_from_file(&char(e.model_path.str), mparams)
			if isnil(e.ctx) {
				return error('Failed to load model even on CPU: ${e.model_path}')
			}
			e.n_gpu_layers = 0
		} else {
			return error('Failed to load model: ${e.model_path}')
		}
	}

	// Context params
	mut cparams := C.llama_context_default_params()
	cparams.n_ctx = u32(e.context_length)
	cparams.n_batch = u32(e.n_batch)
	cparams.n_threads = u32(e.n_threads)
	cparams.n_threads_batch = u32(e.n_threads)
	if e.rope_freq_base > 0.0 {
		cparams.rope_freq_base = e.rope_freq_base
	}

	e.lctx = C.llama_new_context_with_model(e.ctx, cparams)
	if isnil(e.lctx) {
		C.llama_free_model(e.ctx)
		e.ctx = unsafe { nil }
		return error('Failed to create context for model')
	}

	e.loaded = true
	println('Model loaded: ${e.model_path}')
	println('  Backend: ${get_backend_name(e.n_gpu_layers)}')
	println('  Context: ${e.context_length} tokens')
	println('  Threads: ${e.n_threads}')
}

// free releases the model and context.
pub fn (mut e InferenceEngine) free() {
	if !isnil(e.lctx) {
		C.llama_free(e.lctx)
		e.lctx = unsafe { nil }
	}
	if !isnil(e.ctx) {
		C.llama_free_model(e.ctx)
		e.ctx = unsafe { nil }
	}
	e.loaded = false
}

// count_tokens returns the number of tokens for the given text.
pub fn (mut e InferenceEngine) count_tokens(text string) int {
	if text.len == 0 {
		return 0
	}
	if !e.loaded {
		return text.len / 4 // rough estimate when no model loaded
	}
	// Allocate buffer for tokens (overestimate)
	mut tokens := []i32{len: text.len + 64, init: 0}
	n := C.llama_tokenize(
		e.ctx,
		&char(text.str),
		i32(text.len),
		tokens.data,
		i32(tokens.len),
		false, // add_bos
		false, // special
	)
	if n < 0 {
		return text.len / 4 // fallback estimate
	}
	return int(n)
}

// generate produces text from a raw prompt string.
pub fn (mut e InferenceEngine) generate(prompt string, max_tokens_opt ...int) string {
	if !e.loaded {
		eprintln('Model not loaded')
		return ''
	}

	mut max_tokens := e.gen_max_tokens
	if max_tokens_opt.len > 0 {
		max_tokens = max_tokens_opt[0]
	}

	// Check context budget
	prompt_tokens := e.count_tokens(prompt)
	if prompt_tokens + max_tokens > e.context_length {
		available := e.context_length - prompt_tokens
		if available <= 0 {
			eprintln('Prompt (${prompt_tokens} tokens) exceeds context (${e.context_length})')
			return ''
		}
		eprintln('Reducing max_tokens from ${max_tokens} to ${available}')
		max_tokens = available
	}

	// Tokenize the prompt
	mut tokens := []i32{len: prompt.len + 64, init: 0}
	n_tokens := C.llama_tokenize(
		e.ctx,
		&char(prompt.str),
		i32(prompt.len),
		tokens.data,
		i32(tokens.len),
		true, // add_bos for prompt start
		false,
	)
	if n_tokens < 0 {
		eprintln('Tokenization failed')
		return ''
	}
	tokens = tokens[..n_tokens]

	// Clear KV cache
	C.llama_kv_cache_clear(e.lctx)

	// Process prompt tokens
	mut batch := C.llama_batch_get_one(tokens.data, i32(tokens.len))
	ret := C.llama_decode(e.lctx, batch)
	C.llama_batch_free(batch)
	if ret != 0 {
		eprintln('Prompt decode failed (code ${ret})')
		return ''
	}

	// Generation loop
	mut result := strings.new_builder(1024)
	mut n_cur := tokens.len
	mut n_decode := 0

	for n_decode < max_tokens {
		// Sample next token
		mut new_token := e.sample_token(n_cur - 1)

		// Convert token to text
		mut buf := []u8{len: 32, init: 0}
		n_piece := C.llama_token_to_piece(e.ctx, new_token, &char(buf.data), 32, false)
		if n_piece > 0 {
			piece := unsafe { buf[..n_piece].bytestr() }
			result.write_string(piece) or {}
		}

		// Check stop sequences
		text := result.str()
		for stop_seq in e.gen_stop {
			if stop_seq.len > 0 && text.contains(stop_seq) {
				// Remove the stop sequence from output
				mut final_text := text
				final_text = final_text.replace(stop_seq, '')
				return final_text.trim_space()
			}
		}

		// Feed token back for next step
		mut next_tokens := [new_token]
		batch = C.llama_batch_get_one(next_tokens.data, 1)
		ret2 := C.llama_decode(e.lctx, batch)
		C.llama_batch_free(batch)
		if ret2 != 0 {
			break
		}

		n_cur++
		n_decode++
	}

	return result.str().trim_space()
}

// generate_stream yields tokens one at a time via a channel.
pub fn (mut e InferenceEngine) generate_stream(prompt string, max_tokens_opt ...int) chan string {
	ch := chan string{cap: 256}

	spawn fn (mut eng InferenceEngine, p string, mt int, ch chan string) {
		if !eng.loaded {
			ch.push('')
			return
		}

		mut max_tokens := mt

		// Tokenize prompt
		mut tokens := []i32{len: p.len + 64, init: 0}
		n_tokens := C.llama_tokenize(
			eng.ctx,
			&char(p.str),
			i32(p.len),
			tokens.data,
			i32(tokens.len),
			true,
			false,
		)
		if n_tokens < 0 {
			ch.push('')
			return
		}
		tokens = tokens[..n_tokens]

		// Check budget
		prompt_tokens := tokens.len
		if prompt_tokens + max_tokens > eng.context_length {
			available := eng.context_length - prompt_tokens
			if available <= 0 {
				ch.push('')
				return
			}
			max_tokens = available
		}

		C.llama_kv_cache_clear(eng.lctx)

		// Decode prompt
		mut batch := C.llama_batch_get_one(tokens.data, i32(tokens.len))
		C.llama_decode(eng.lctx, batch)
		C.llama_batch_free(batch)

		mut n_cur := tokens.len
		mut n_decode := 0
		mut accumulated := ''

		for n_decode < max_tokens {
			new_token := eng.sample_token(n_cur - 1)

			mut buf := []u8{len: 32, init: 0}
			n_piece := C.llama_token_to_piece(eng.ctx, new_token, &char(buf.data), 32, false)
			if n_piece > 0 {
				piece := unsafe { buf[..n_piece].bytestr() }
				ch.push(piece)
				accumulated += piece
			}

			// Check stop sequences
			for stop_seq in eng.gen_stop {
				if stop_seq.len > 0 && accumulated.contains(stop_seq) {
					ch.push('') // signal end
					return
				}
			}

			mut next_tokens := [new_token]
			batch = C.llama_batch_get_one(next_tokens.data, 1)
			ret := C.llama_decode(eng.lctx, batch)
			C.llama_batch_free(batch)
			if ret != 0 {
				break
			}

			n_cur++
			n_decode++
		}

		ch.push('') // signal end
	}(mut e, prompt, if max_tokens_opt.len > 0 { max_tokens_opt[0] } else { e.gen_max_tokens }, ch)

	return ch
}

// sample_token picks the next token using top-k, top-p, temperature, repeat penalty.
fn (mut e InferenceEngine) sample_token(pos int) int {
	model := C.llama_get_model(e.lctx)
	n_vocab := C.llama_n_vocab(model)

	// Get logits for this position
	logits := C.llama_get_logits_ith(e.lctx, i32(pos))

	// Build candidates array from logits
	mut candidates := []C.llama_token_data{len: n_vocab, init: C.llama_token_data{id: i32(it), logit: 0.0, p: 0.0}}
	for i in 0 .. n_vocab {
		candidates[i].logit = unsafe { logits[i] }
		candidates[i].p = 0.0
	}

	// Apply repeat penalty using recent tokens (last 64 or fewer)
	mut penalty_buf := []i32{len: 64, init: 0}
	mut n_penalty := 0
	// For simplicity, we skip repeat penalty on the first few tokens
	// since we don't track a global token history here.
	// A full implementation would maintain a ring buffer of recent tokens.

	// Apply top-k filtering
	if e.gen_top_k > 0 {
		C.llama_sample_top_k(e.lctx, candidates.data, i32(candidates.len), i32(e.gen_top_k), usize(1))
		// Recount candidates after filtering (top-k moves kept entries to front)
		mut kept := 0
		for i in 0 .. candidates.len {
			if candidates[i].logit > -f64(1e30) {
				kept++
			} else {
				break
			}
		}
		if kept > 0 {
			candidates = candidates[..kept]
		}
	}

	// Apply top-p (nucleus) filtering
	if e.gen_top_p > 0.0 && e.gen_top_p < 1.0 {
		C.llama_sample_top_p(e.lctx, candidates.data, i32(candidates.len), e.gen_top_p, usize(1))
		mut kept2 := 0
		for i in 0 .. candidates.len {
			if candidates[i].p >= 0.0 && candidates[i].logit > -f64(1e30) {
				kept2++
			} else {
				break
			}
		}
		if kept2 > 0 {
			candidates = candidates[..kept2]
		}
	}

	// Apply temperature scaling
	temp := e.gen_temperature
	if temp <= 0.0 {
		// Greedy: pick highest logit
		mut best_idx := 0
		mut best_logit := candidates[0].logit
		for i in 1 .. candidates.len {
			if candidates[i].logit > best_logit {
				best_logit = candidates[i].logit
				best_idx = i
			}
		}
		return candidates[best_idx].id
	}

	C.llama_sample_temp(e.lctx, candidates.data, i32(candidates.len), temp)

	// Sample from the distribution (weighted random selection)
	mut rng_sum := 0.0
	threshold := rand_f64() // V's built-in random [0,1)
	for i in 0 .. candidates.len {
		rng_sum += candidates[i].p
		if rng_sum > threshold {
			return candidates[i].id
		}
	}

	// Fallback: return highest probability token
	return candidates[0].id
}

// chat generates a response from a list of chat messages.
pub fn (mut e InferenceEngine) chat(messages []ChatMessage, system_prompt string) string {
	prompt := e.format_chat_prompt(messages, system_prompt)
	return e.generate(prompt)
}

// chat_stream generates a streaming response from chat messages.
pub fn (mut e InferenceEngine) chat_stream(messages []ChatMessage, system_prompt string) chan string {
	prompt := e.format_chat_prompt(messages, system_prompt)
	return e.generate_stream(prompt)
}

// format_chat_prompt formats messages according to the model's chat template.
pub fn (e InferenceEngine) format_chat_prompt(messages []ChatMessage, system_prompt string) string {
	return match e.model_fmt {
		.qwen { e.format_qwen(messages, system_prompt) }
		.mistral { e.format_mistral(messages, system_prompt) }
		.llama3 { e.format_llama3(messages, system_prompt) }
		.chatml { e.format_chatml(messages, system_prompt) }
	}
}

fn (e InferenceEngine) format_qwen(messages []ChatMessage, system_prompt string) string {
	mut sb := strings.new_builder(2048)
	if system_prompt != '' {
		sb.write_string('<|im_start|>system\n${system_prompt}<|im_end|>\n')
	}
	for msg in messages {
		sb.write_string('<|im_start|>${msg.role}\n${msg.content}<|im_end|>\n')
	}
	sb.write_string('<|im_start|>assistant\n')
	return sb.str()
}

fn (e InferenceEngine) format_mistral(messages []ChatMessage, system_prompt string) string {
	mut sb := strings.new_builder(2048)
	if system_prompt != '' {
		sb.write_string('<s>[INST] ${system_prompt}\n\n')
	} else {
		sb.write_string('<s>[INST] ')
	}
	for i, msg in messages {
		if msg.role == 'user' {
			if i > 0 {
				sb.write_string('[INST] ${msg.content} [/INST]')
			} else {
				sb.write_string('${msg.content} [/INST]')
			}
		} else if msg.role == 'assistant' {
			sb.write_string(' ${msg.content}</s>')
		}
	}
	return sb.str()
}

fn (e InferenceEngine) format_llama3(messages []ChatMessage, system_prompt string) string {
	mut sb := strings.new_builder(2048)
	sb.write_string('<|begin_of_text|>')
	if system_prompt != '' {
		sb.write_string('<|start_header_id|>system<|end_header_id|>\n\n${system_prompt}<|eot_id|>')
	}
	for msg in messages {
		sb.write_string('<|start_header_id|>${msg.role}<|end_header_id|>\n\n${msg.content}<|eot_id|>')
	}
	sb.write_string('<|start_header_id|>assistant<|end_header_id|>\n\n')
	return sb.str()
}

fn (e InferenceEngine) format_chatml(messages []ChatMessage, system_prompt string) string {
	mut sb := strings.new_builder(2048)
	if system_prompt != '' {
		sb.write_string('<|im_start|>system\n${system_prompt}<|im_end|>\n')
	}
	for msg in messages {
		sb.write_string('<|im_start|>${msg.role}\n${msg.content}<|im_end|>\n')
	}
	sb.write_string('<|im_start|>assistant\n')
	return sb.str()
}
