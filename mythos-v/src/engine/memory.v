module engine

import os
import json
import time
import config

// ConversationMemory manages chat history with persistence.
pub struct ConversationMemory {
pub mut:
	messages         []ChatMessage
	metadata         MemoryMetadata
	conversations_dir string
	max_history_turns int
	auto_save        bool
	tags             []string
	bookmarks        []Bookmark
	branches         map[string][]ChatMessage
	active_branch    string
	branch_point     int
}

pub struct MemoryMetadata {
pub mut:
	created_at string
	model      string
}

pub struct Bookmark {
pub:
	index     int
	timestamp string
	note      string
}

// new_conversation_memory creates a memory manager from config.
pub fn new_conversation_memory(cfg config.Config) ConversationMemory {
	conv_dir := cfg.memory.conversations_dir
	if !os.exists(conv_dir) {
		os.mkdir(conv_dir) or {}
	}

	return ConversationMemory{
		messages: []
		metadata: MemoryMetadata{
			created_at: time.now().format('2006-01-02T15:04:05')
			model: ''
		}
		conversations_dir: conv_dir
		max_history_turns: cfg.memory.max_history_turns
		auto_save: cfg.memory.save_conversations
		tags: []
		bookmarks: []
		branches: {}
		active_branch: 'main'
		branch_point: 0
	}
}

// add_message adds a message to the conversation history.
pub fn (mut m ConversationMemory) add_message(role string, content string) {
	m.messages << ChatMessage{role, content}

	// Trim if exceeding max turns
	if m.messages.len > m.max_history_turns * 2 {
		m.trim_history()
	}
}

// trim_history keeps system messages and recent history.
pub fn (mut m ConversationMemory) trim_history() {
	mut system_msgs := []ChatMessage{}
	mut recent_msgs := []ChatMessage{}

	for msg in m.messages {
		if msg.role == 'system' {
			system_msgs << msg
		} else {
			recent_msgs << msg
		}
	}

	max_keep := m.max_history_turns * 2
	if recent_msgs.len > max_keep {
		recent_msgs = recent_msgs[recent_msgs.len - max_keep..]
	}

	m.messages = []ChatMessage{}
	m.messages << system_msgs
	m.messages << recent_msgs
}

// get_messages returns messages for inference, optionally filtering system messages.
pub fn (m ConversationMemory) get_messages(include_system bool) []ChatMessage {
	if include_system {
		return m.messages.clone()
	}
	mut result := []ChatMessage{}
	for msg in m.messages {
		if msg.role != 'system' {
			result << msg
		}
	}
	return result
}

// clear resets the conversation.
pub fn (mut m ConversationMemory) clear() {
	m.messages = []
	m.tags = []
	m.bookmarks = []
	m.metadata = MemoryMetadata{
		created_at: time.now().format('2006-01-02T15:04:05')
		model: m.metadata.model
	}
}

// save persists the conversation to a JSON file.
pub fn (m ConversationMemory) save(filename string) ! {
	if !m.auto_save {
		return
	}

	path := os.join_path(m.conversations_dir, filename)
	data := ConversationFile{
		metadata: m.metadata
		messages: m.messages
		tags: m.tags
		bookmarks: m.bookmarks
	}
	json_bytes := json.encode(data)
	os.write_file(path, json_bytes)!
}

// load reads a conversation from a JSON file.
pub fn (mut m ConversationMemory) load(filename string) ! {
	path := os.join_path(m.conversations_dir, filename)
	content := os.read_file(path)!
	data := json.decode(ConversationFile, content) or {
		return error('Failed to parse conversation file: ${err}')
	}
	m.messages = data.messages
	m.metadata = data.metadata
	m.tags = data.tags
	m.bookmarks = data.bookmarks
}

// ConversationFile is the JSON structure for saved conversations.
struct ConversationFile {
	metadata MemoryMetadata
	messages []ChatMessage
	tags     []string
	bookmarks []Bookmark
}

// last_user_message returns the most recent user message, or empty string.
pub fn (m ConversationMemory) last_user_message() string {
	for i := m.messages.len - 1; i >= 0; i-- {
		if m.messages[i].role == 'user' {
			return m.messages[i].content
		}
	}
	return ''
}

// message_count returns the number of messages.
pub fn (m ConversationMemory) message_count() int {
	return m.messages.len
}

// create_branch creates a new branch from the current branch point.
pub fn (mut m ConversationMemory) create_branch(name string) {
	m.branches[m.active_branch] = m.messages[..m.branch_point].clone()
	m.active_branch = name
}

// add_bookmark adds a bookmark at the current message index.
pub fn (mut m ConversationMemory) add_bookmark(note string) {
	m.bookmarks << Bookmark{
		index: m.messages.len - 1
		timestamp: time.now().format('2006-01-02T15:04:05')
		note: note
	}
}

// add_tag adds a tag to this conversation.
pub fn (mut m ConversationMemory) add_tag(tag string) {
	if tag !in m.tags {
		m.tags << tag
	}
}
