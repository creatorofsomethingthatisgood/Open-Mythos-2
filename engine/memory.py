"""
Conversation Memory - Manages conversation history and persistence
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
import yaml

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Manages conversation history with persistence"""

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize ConversationMemory

        Args:
            config_path: Path to configuration file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()

        # Setup conversations directory
        conv_dir = self.config.get('memory', {}).get('conversations_dir', 'conversations')
        self.conversations_dir = Path(conv_dir)
        self.conversations_dir.mkdir(exist_ok=True)

        # Current conversation
        self.messages: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {
            'created_at': datetime.now().isoformat(),
            'model': None,
            'config': {}
        }

        # Configuration
        self.max_history_turns = self.config.get('memory', {}).get('max_history_turns', 50)
        self.auto_save = self.config.get('memory', {}).get('save_conversations', True)

        # Tags
        self.tags: List[str] = []

        # Bookmarks (each: message_index, timestamp, note)
        self.bookmarks: List[Dict] = []

        # Branching support
        self.branches: Dict[str, List[Dict]] = {}
        self.active_branch: str = "main"
        self._branch_point: int = 0

    def _load_config(self) -> Dict:
        """Load configuration from YAML"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}

    def add_message(self, role: str, content: str, **kwargs):
        """
        Add a message to the conversation

        Args:
            role: Message role (user/assistant/system)
            content: Message content
            **kwargs: Additional metadata
        """
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }
        self.messages.append(message)

        # Trim history if needed
        if len(self.messages) > self.max_history_turns * 2:  # *2 for user+assistant pairs
            self._trim_history()

    def _trim_history(self, engine=None):
        """
        Trim conversation history to max turns.

        When engine is provided and config has auto_summarize: true,
        calls compact_with_summary() instead of hard deletion.

        Args:
            engine: Optional inference engine for summarization
        """
        auto_summarize = self.config.get('memory', {}).get('auto_summarize', False)

        if engine is not None and auto_summarize:
            try:
                result = self.compact_with_summary(engine)
                logger.info(
                    f"Auto-summarized conversation: {result['before']} -> {result['after']} messages"
                )
                return
            except Exception as e:
                logger.warning(f"Auto-summarize failed, falling back to hard trim: {e}")

        # Keep system messages and recent history
        system_messages = [msg for msg in self.messages if msg['role'] == 'system']
        recent_messages = [msg for msg in self.messages if msg['role'] != 'system']

        # Keep only last N turns
        if len(recent_messages) > self.max_history_turns * 2:
            recent_messages = recent_messages[-(self.max_history_turns * 2):]

        self.messages = system_messages + recent_messages
        logger.info(f"Trimmed conversation history to {len(self.messages)} messages")

    def get_messages(self, include_system: bool = True) -> List[Dict[str, str]]:
        """
        Get conversation messages

        Args:
            include_system: Whether to include system messages

        Returns:
            List of messages
        """
        if include_system:
            return [{'role': msg['role'], 'content': msg['content']} for msg in self.messages]
        else:
            return [
                {'role': msg['role'], 'content': msg['content']}
                for msg in self.messages
                if msg['role'] != 'system'
            ]

    def get_recent_context(self, max_turns: int = 10) -> List[Dict[str, str]]:
        """
        Get recent conversation context

        Args:
            max_turns: Maximum number of turns to include

        Returns:
            Recent messages
        """
        # Get non-system messages
        non_system = [msg for msg in self.messages if msg['role'] != 'system']

        # Get last N messages
        recent = non_system[-(max_turns * 2):]

        return [{'role': msg['role'], 'content': msg['content']} for msg in recent]

    def clear(self):
        """Clear conversation history"""
        self.messages = []
        self.metadata['created_at'] = datetime.now().isoformat()
        logger.info("Conversation cleared")

    def _validate_path(self, filename: str) -> Path:
        """Resolve filename and reject path-traversal attempts."""
        filepath = (self.conversations_dir / filename).resolve()
        if not filepath.is_relative_to(self.conversations_dir.resolve()):
            raise ValueError(f"Path traversal rejected: {filename}")
        return filepath

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """
        Sanitize a conversation name for filesystem safety.

        Allows alphanumeric, dash, underscore. Max 50 chars.

        Args:
            name: Raw name string

        Returns:
            Sanitized name
        """
        sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
        sanitized = sanitized[:50]
        sanitized = sanitized.strip('_-')
        return sanitized

    def save(self, filename: Optional[str] = None) -> Path:
        """
        Save conversation to file.

        When self.metadata has a 'name' entry, the filename includes it:
        conversation_<name>_<timestamp>.json

        Args:
            filename: Optional filename (auto-generated if None)

        Returns:
            Path to saved file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            conv_name = self.metadata.get('name')
            if conv_name:
                safe_name = self._sanitize_name(str(conv_name))
                if safe_name:
                    filename = f"conversation_{safe_name}_{timestamp}.json"
                else:
                    filename = f"conversation_{timestamp}.json"
            else:
                filename = f"conversation_{timestamp}.json"

        filepath = self._validate_path(filename)

        try:
            conversation_data = {
                'metadata': self.metadata,
                'messages': self.messages,
                'tags': self.tags,
                'bookmarks': self.bookmarks,
                'branches': self.branches,
                'active_branch': self.active_branch,
                'branch_point': self._branch_point,
            }

            with open(filepath, 'w') as f:
                json.dump(conversation_data, f, indent=2)

            logger.info(f"Conversation saved to: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Failed to save conversation: {e}")
            raise

    def save_full(self, session_state: dict) -> Path:
        """
        Save conversation with full session state merged into metadata.

        Merges session_state keys into metadata before saving, so the JSON
        includes system_prompt_file, rag_enabled, rml_enabled,
        generation_params, model_path, conversation_name, tags, bookmarks,
        active_branch, etc.

        Args:
            session_state: Dict of extra session fields to merge into metadata

        Returns:
            Path to saved file
        """
        self.metadata.update(session_state)
        # If session_state provides a name, also set it on metadata for filename
        if 'name' not in self.metadata and 'conversation_name' in session_state:
            self.metadata['name'] = session_state['conversation_name']
        return self.save()

    def load(self, filename: str) -> bool:
        """
        Load conversation from file

        Args:
            filename: Filename to load

        Returns:
            True if successful
        """
        try:
            filepath = self._validate_path(filename)
        except ValueError:
            logger.error(f"Invalid filename: {filename}")
            return False

        if not filepath.exists():
            logger.error(f"Conversation file not found: {filepath}")
            return False

        try:
            with open(filepath, 'r') as f:
                conversation_data = json.load(f)

            self.messages = conversation_data.get('messages', [])
            self.metadata = conversation_data.get('metadata', {})

            # Restore tags, bookmarks, branches (backward compatible)
            self.tags = conversation_data.get('tags', [])
            self.bookmarks = conversation_data.get('bookmarks', [])
            self.branches = conversation_data.get('branches', {})
            self.active_branch = conversation_data.get('active_branch', 'main')
            self._branch_point = conversation_data.get('branch_point', 0)

            logger.info(f"Conversation loaded from: {filepath}")
            logger.info(f"Loaded {len(self.messages)} messages")
            return True

        except Exception as e:
            logger.error(f"Failed to load conversation: {e}")
            return False

    def load_full(self, filename: str) -> Optional[Dict]:
        """
        Load conversation and return both messages and session_state dict.

        Session state includes the extra metadata fields that were saved
        via save_full (system_prompt_file, rag_enabled, rml_enabled,
        generation_params, model_path, conversation_name, etc.)

        Args:
            filename: Filename to load

        Returns:
            Dict with 'messages' and 'session_state' keys, or None on failure
        """
        try:
            filepath = self._validate_path(filename)
        except ValueError:
            logger.error(f"Invalid filename: {filename}")
            return None

        if not filepath.exists():
            logger.error(f"Conversation file not found: {filepath}")
            return None

        try:
            with open(filepath, 'r') as f:
                conversation_data = json.load(f)

            messages = conversation_data.get('messages', [])
            metadata = conversation_data.get('metadata', {})

            # Build session_state from known session-level fields
            session_state = {}
            for key in (
                'system_prompt_file', 'rag_enabled', 'rml_enabled',
                'generation_params', 'model_path', 'conversation_name',
                'name', 'tags', 'bookmarks', 'active_branch',
            ):
                if key in metadata:
                    session_state[key] = metadata[key]
                elif key in conversation_data:
                    session_state[key] = conversation_data[key]

            # Also restore into self for consistency
            self.messages = messages
            self.metadata = metadata
            self.tags = conversation_data.get('tags', [])
            self.bookmarks = conversation_data.get('bookmarks', [])
            self.branches = conversation_data.get('branches', {})
            self.active_branch = conversation_data.get('active_branch', 'main')
            self._branch_point = conversation_data.get('branch_point', 0)

            logger.info(f"Full conversation loaded from: {filepath}")
            logger.info(f"Loaded {len(messages)} messages with session state")
            return {'messages': messages, 'session_state': session_state}

        except Exception as e:
            logger.error(f"Failed to load full conversation: {e}")
            return None

    # ---- Tags ----

    def add_tag(self, tag: str):
        """
        Add a tag to the conversation.

        Args:
            tag: Tag string to add
        """
        if tag and tag not in self.tags:
            self.tags.append(tag)
            logger.debug(f"Tag added: {tag}")

    def remove_tag(self, tag: str):
        """
        Remove a tag from the conversation.

        Args:
            tag: Tag string to remove
        """
        if tag in self.tags:
            self.tags.remove(tag)
            logger.debug(f"Tag removed: {tag}")

    def list_tags(self) -> List[str]:
        """
        List all tags on the conversation.

        Returns:
            List of tag strings
        """
        return list(self.tags)

    # ---- Bookmarks ----

    def add_bookmark(self, message_index: int, note: str = ""):
        """
        Add a bookmark at a given message index.

        Args:
            message_index: Index into self.messages
            note: Optional note for the bookmark
        """
        bookmark = {
            'message_index': message_index,
            'timestamp': datetime.now().isoformat(),
            'note': note,
        }
        self.bookmarks.append(bookmark)
        logger.debug(f"Bookmark added at index {message_index}")

    def remove_bookmark(self, index: int):
        """
        Remove a bookmark by its position in the bookmarks list.

        Args:
            index: Index into self.bookmarks
        """
        if 0 <= index < len(self.bookmarks):
            removed = self.bookmarks.pop(index)
            logger.debug(f"Bookmark removed: {removed}")
        else:
            logger.warning(f"Bookmark index out of range: {index}")

    def list_bookmarks(self) -> List[Dict]:
        """
        List all bookmarks.

        Returns:
            List of bookmark dicts (message_index, timestamp, note)
        """
        return list(self.bookmarks)

    # ---- Cross-conversation search ----

    def search_conversations(self, query: str) -> List[Dict]:
        """
        Search all saved conversations for a case-insensitive substring match.

        Matches against message content, conversation name, and tags.
        Returns a list of result dicts with filename, name, timestamp,
        tags, and snippet (first 150 chars of matching message).

        Args:
            query: Search string

        Returns:
            List of result dicts
        """
        results = []
        query_lower = query.lower()

        if not self.conversations_dir.exists():
            return results

        for filepath in self.conversations_dir.glob("conversation_*.json"):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
            except Exception:
                continue

            metadata = data.get('metadata', {})
            name = metadata.get('name', '')
            tags = data.get('tags', [])
            timestamp = metadata.get('created_at', '')

            matched = False
            snippet = ""

            # Check name
            if query_lower in name.lower():
                matched = True

            # Check tags
            for tag in tags:
                if query_lower in tag.lower():
                    matched = True
                    break

            # Check messages
            for msg in data.get('messages', []):
                content = msg.get('content', '')
                if query_lower in content.lower():
                    matched = True
                    snippet = content[:150]
                    break

            if matched:
                results.append({
                    'filename': filepath.name,
                    'name': name,
                    'timestamp': timestamp,
                    'tags': tags,
                    'snippet': snippet,
                })

        return results

    # ---- LLM-powered compaction ----

    def compact_with_summary(self, engine, keep_recent: int = 20) -> Dict:
        """
        Summarize older messages using the LLM and replace them with a
        single compact-summary system message.

        Bookmarked messages are preserved (summarization will not remove
        messages at or before a bookmarked index).

        Args:
            engine: Inference engine with a generate() method
            keep_recent: Number of most recent non-system turns to keep

        Returns:
            Dict with before, after, summary_length
        """
        before_count = len(self.messages)

        # Find the boundary: keep the most recent keep_recent non-system turns
        non_system_indices = [
            i for i, msg in enumerate(self.messages) if msg['role'] != 'system'
        ]

        if len(non_system_indices) <= keep_recent:
            # Nothing to compact
            return {
                'before': before_count,
                'after': before_count,
                'summary_length': 0,
            }

        cutoff_index = non_system_indices[-keep_recent]

        # Collect bookmarked indices so we never summarize past them
        bookmark_indices = {b['message_index'] for b in self.bookmarks}
        if bookmark_indices:
            earliest_bookmark = min(bookmark_indices)
            if earliest_bookmark < cutoff_index:
                cutoff_index = earliest_bookmark

        # Split messages
        old_messages = self.messages[:cutoff_index]
        recent_messages = self.messages[cutoff_index:]

        if not old_messages:
            return {
                'before': before_count,
                'after': before_count,
                'summary_length': 0,
            }

        # Build text for summarization
        segment_lines = []
        for msg in old_messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            segment_lines.append(f"[{role}]: {content}")

        segment_text = "\n\n".join(segment_lines)

        summary = None

        # Try LLM summarization
        if engine is not None:
            try:
                prompt = (
                    "Summarize this conversation segment in 2-3 paragraphs, "
                    "preserving key decisions, code written, questions answered, "
                    "and context needed for continuity.\n\n"
                    f"{segment_text}"
                )
                response = engine.generate(
                    prompt,
                    stream=False,
                    max_tokens=512,
                    temperature=0.3,
                )
                if response:
                    summary = response.strip()
            except Exception as e:
                logger.warning(f"LLM summarization failed: {e}")

        # Fallback: crude truncation
        if summary is None:
            # Keep first and last few messages as a crude summary
            kept = []
            if len(old_messages) > 4:
                kept.append(old_messages[0])
                kept.append(old_messages[-1])
            else:
                kept = old_messages
            summary_parts = []
            for msg in kept:
                content = msg.get('content', '')
                summary_parts.append(content[:200])
            summary = (
                "[TRUNCATED SUMMARY] "
                + " ... ".join(summary_parts)
            )

        summary_message = {
            'role': 'system',
            'content': f"[CONVERSATION SUMMARY]\n{summary}",
            'compact_summary': True,
            'timestamp': datetime.now().isoformat(),
        }

        self.messages = [summary_message] + recent_messages
        after_count = len(self.messages)

        return {
            'before': before_count,
            'after': after_count,
            'summary_length': len(summary),
        }

    # ---- Branching ----

    def create_branch(self, name: str) -> bool:
        """
        Create a new branch from the current conversation state.

        Saves current messages (up to current position) as the branch.
        The branch point is recorded as len(self.messages).

        Args:
            name: Name for the new branch

        Returns:
            True if successful
        """
        if name in self.branches:
            logger.warning(f"Branch already exists: {name}")
            return False

        # Save current branch before creating new one
        self.branches[self.active_branch] = list(self.messages)
        self._branch_point = len(self.messages)

        # New branch starts from the same messages up to branch point
        self.branches[name] = list(self.messages[:self._branch_point])
        self.active_branch = name
        logger.info(f"Created branch: {name} at index {self._branch_point}")
        return True

    def switch_branch(self, name: str) -> bool:
        """
        Switch to a different branch.

        Saves the current branch messages and loads the target branch.

        Args:
            name: Name of the branch to switch to

        Returns:
            True if branch exists and switch succeeded
        """
        if name not in self.branches and name != "main":
            logger.warning(f"Branch not found: {name}")
            return False

        # Save current branch
        self.branches[self.active_branch] = list(self.messages)

        # Load target branch
        if name == "main" and "main" not in self.branches:
            # Main branch starts empty if never saved
            self.branches["main"] = []

        self.active_branch = name
        self.messages = list(self.branches.get(name, []))
        logger.info(f"Switched to branch: {name}")
        return True

    def list_branches(self) -> List[Dict]:
        """
        List all branches with metadata.

        Returns:
            List of dicts with name, message_count, branch_point
        """
        result = []
        for branch_name, branch_messages in self.branches.items():
            result.append({
                'name': branch_name,
                'message_count': len(branch_messages),
                'branch_point': self._branch_point,
            })
        # Include the active branch if not in self.branches yet
        if self.active_branch not in self.branches:
            result.append({
                'name': self.active_branch,
                'message_count': len(self.messages),
                'branch_point': self._branch_point,
            })
        return result

    def merge_branch(self, name: str) -> bool:
        """
        Merge a branch into the current active branch.

        Appends the target branch's messages after the current branch point.

        Args:
            name: Name of the branch to merge

        Returns:
            True if merge succeeded
        """
        if name not in self.branches:
            logger.warning(f"Branch not found for merge: {name}")
            return False

        if name == self.active_branch:
            logger.warning("Cannot merge a branch into itself")
            return False

        source_messages = self.branches[name]

        # Append messages from the source branch that are after the branch point
        if self._branch_point < len(source_messages):
            messages_to_append = source_messages[self._branch_point:]
            self.messages.extend(messages_to_append)
            logger.info(
                f"Merged branch '{name}': appended {len(messages_to_append)} messages"
            )
            return True
        else:
            logger.info(f"Branch '{name}' has no messages after branch point to merge")
            return True

    def list_conversations(self) -> List[Path]:
        """
        List saved conversations

        Returns:
            List of conversation file paths
        """
        conversations = list(self.conversations_dir.glob("conversation_*.json"))
        return sorted(conversations, reverse=True)  # Most recent first

    def export_text(self) -> str:
        """
        Export conversation as plain text

        Returns:
            Formatted conversation text
        """
        lines = []
        lines.append("=" * 70)
        lines.append(f"Conversation Export - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 70)
        lines.append("")

        for msg in self.messages:
            role = msg['role'].upper()
            content = msg['content']
            timestamp = msg.get('timestamp', '')

            lines.append(f"[{role}] {timestamp}")
            lines.append(content)
            lines.append("")
            lines.append("-" * 70)
            lines.append("")

        return "\n".join(lines)

    def set_metadata(self, key: str, value: Any):
        """
        Set metadata field

        Args:
            key: Metadata key
            value: Metadata value
        """
        self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """
        Get metadata field

        Args:
            key: Metadata key
            default: Default value if key not found

        Returns:
            Metadata value
        """
        return self.metadata.get(key, default)
