module engine

import net.http
import json
import os
import io
import strings
import config

// Provider presets for cloud inference.
pub struct ProviderPreset {
pub:
	base_url string
	model    string
}

pub fn providers() map[string]ProviderPreset {
	return {
		'openai':   ProviderPreset{'https://api.openai.com/v1', 'gpt-4o-mini'}
		'nvidia':   ProviderPreset{'https://integrate.api.nvidia.com/v1', 'meta/llama-3.3-70b-instruct'}
		'together': ProviderPreset{'https://api.together.xyz/v1', 'meta-llama/Llama-3.3-70B-Instruct-Turbo'}
		'groq':     ProviderPreset{'https://api.groq.com/openai/v1', 'llama-3.3-70b-versatile'}
	}
}

// CloudInferenceEngine calls OpenAI-compatible API endpoints.
// Drop-in replacement for InferenceEngine when cloud mode is active.
pub struct CloudInferenceEngine {
pub mut:
	api_key        string
	base_url       string
	model_name     string
	context_length int
	temperature    f64
	top_p          f64
	max_tokens     int
}

// new_cloud_engine creates a cloud engine from config.
pub fn new_cloud_engine(cfg config.Config) !CloudInferenceEngine {
	mut api_key := cfg.cloud.api_key
	if api_key == '' {
		api_key = os.getenv('MYTHOS_API_KEY')
	}
	if api_key == '' {
		return error('No API key. Set MYTHOS_API_KEY or config cloud.api_key')
	}

	// Resolve provider preset
	mut base_url := cfg.cloud.base_url
	mut model_name := cfg.cloud.model
	prov := providers()
	if cfg.cloud.provider in prov {
		preset := prov[cfg.cloud.provider]
		if base_url == '' {
			base_url = preset.base_url
		}
		if model_name == '' {
			model_name = preset.model
		}
	}

	// Strip trailing slash
	if base_url.ends_with('/') {
		base_url = base_url[..base_url.len - 1]
	}

	return CloudInferenceEngine{
		api_key: api_key
		base_url: base_url
		model_name: model_name
		context_length: 128000
		temperature: cfg.generation.temperature
		top_p: cfg.generation.top_p
		max_tokens: cfg.generation.max_tokens
	}
}

// count_tokens returns a rough estimate (~4 chars per token).
pub fn (e CloudInferenceEngine) count_tokens(text string) int {
	if text.len == 0 {
		return 0
	}
	mut estimate := text.len / 4
	if estimate == 0 {
		estimate = 1
	}
	return estimate
}

// ApiMessage is a message for the OpenAI chat completions API.
struct ApiMessage {
	role    string
	content string
}

// ChatRequest is the JSON body for the chat completions endpoint.
struct ChatRequest {
	model       string
	messages    []ApiMessage
	max_tokens  int
	temperature f64
	top_p       f64
	stream      bool
	stop        []string @[if_empty]
}

// ChatResponse is the JSON response from the chat completions endpoint.
struct ChatResponse {
	choices []Choice
}

struct Choice {
	message MessageContent
}

struct MessageContent {
	content string
}

// chat sends a non-streaming chat completion request.
pub fn (mut e CloudInferenceEngine) chat(messages []ChatMessage, system_prompt string) string {
	mut all_messages := []ApiMessage{}
	if system_prompt != '' {
		all_messages << ApiMessage{'system', system_prompt}
	}
	for msg in messages {
		all_messages << ApiMessage{msg.role, msg.content}
	}

	req_body := ChatRequest{
		model: e.model_name
		messages: all_messages
		max_tokens: e.max_tokens
		temperature: e.temperature
		top_p: e.top_p
		stream: false
	}

	body_json := json.encode(req_body)

	url := '${e.base_url}/chat/completions'
	mut req := http.new_request(http.Method.post, url, body_json)!
	req.add_header('Authorization', 'Bearer ${e.api_key}')
	req.add_header('Content-Type', 'application/json')

	resp := req.do() or {
		eprintln('Cloud request failed: ${err}')
		return ''
	}

	if resp.status_code != 200 {
		eprintln('Cloud API error ${resp.status_code}: ${resp.body}')
		return ''
	}

	data := json.decode(ChatResponse, resp.body) or {
		eprintln('Failed to parse cloud response: ${err}')
		return ''
	}

	if data.choices.len == 0 {
		return ''
	}
	return data.choices[0].message.content.trim_space()
}

// generate wraps chat for raw prompt compatibility.
pub fn (mut e CloudInferenceEngine) generate(prompt string) string {
	messages := [ChatMessage{'user', prompt}]
	return e.chat(messages, '')
}

// chat_stream streams tokens from a chat completion request.
// Returns a channel that yields one token string at a time.
pub fn (mut e CloudInferenceEngine) chat_stream(messages []ChatMessage, system_prompt string) chan string {
	ch := chan string{cap: 256}

	spawn fn (mut eng CloudInferenceEngine, msgs []ChatMessage, sp string, ch chan string) {
		mut all_messages := []ApiMessage{}
		if sp != '' {
			all_messages << ApiMessage{'system', sp}
		}
		for msg in msgs {
			all_messages << ApiMessage{msg.role, msg.content}
		}

		req_body := ChatRequest{
			model: eng.model_name
			messages: all_messages
			max_tokens: eng.max_tokens
			temperature: eng.temperature
			top_p: eng.top_p
			stream: true
		}

		body_json := json.encode(req_body)

		url := '${eng.base_url}/chat/completions'
		mut req := http.new_request(http.Method.post, url, body_json) or {
			ch.push('')
			return
		}
		req.add_header('Authorization', 'Bearer ${eng.api_key}')
		req.add_header('Content-Type', 'application/json')

		resp := req.do() or {
			eprintln('Cloud stream request failed: ${err}')
			ch.push('')
			return
		}

		// Parse SSE stream
		for line in resp.body.split_into_lines() {
			if line == '' || !line.starts_with('data: ') {
				continue
			}
			payload := line[6..]
			if payload.trim_space() == '[DONE]' {
				break
			}
			// Parse the SSE chunk JSON
			data := json.decode(StreamChunk, payload) or {
				continue
			}
			if data.choices.len > 0 {
				content := data.choices[0].delta.content
				if content != '' {
					ch.push(content)
				}
			}
		}

		ch.push('') // signal end
	}(mut e, messages, system_prompt, ch)

	return ch
}

// StreamChunk is the JSON structure for SSE streaming chunks.
struct StreamChunk {
	choices []StreamChoice
}

struct StreamChoice {
	delta StreamDelta
}

struct StreamDelta {
	content string
}

// format_chat_prompt is kept for interface compatibility with InferenceEngine.
// Cloud mode sends structured messages, so this just formats them for display.
pub fn (e CloudInferenceEngine) format_chat_prompt(messages []ChatMessage, system_prompt string) string {
	mut sb := strings.new_builder(1024)
	if system_prompt != '' {
		sb.write_string('System: ${system_prompt}\n\n')
	}
	for msg in messages {
		sb.write_string('${msg.role.capitalize()}: ${msg.content}\n\n')
	}
	return sb.str()
}
