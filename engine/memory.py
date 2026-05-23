"""
Conversation Memory - Manages conversation history and persistence
"""

import json
import logging
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
    
    def _trim_history(self):
        """Trim conversation history to max turns"""
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
    
    def save(self, filename: Optional[str] = None) -> Path:
        """
        Save conversation to file
        
        Args:
            filename: Optional filename (auto-generated if None)
            
        Returns:
            Path to saved file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"conversation_{timestamp}.json"
        
        filepath = self.conversations_dir / filename
        
        try:
            conversation_data = {
                'metadata': self.metadata,
                'messages': self.messages
            }
            
            with open(filepath, 'w') as f:
                json.dump(conversation_data, f, indent=2)
            
            logger.info(f"Conversation saved to: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to save conversation: {e}")
            raise
    
    def load(self, filename: str) -> bool:
        """
        Load conversation from file
        
        Args:
            filename: Filename to load
            
        Returns:
            True if successful
        """
        filepath = self.conversations_dir / filename
        
        if not filepath.exists():
            logger.error(f"Conversation file not found: {filepath}")
            return False
        
        try:
            with open(filepath, 'r') as f:
                conversation_data = json.load(f)
            
            self.messages = conversation_data.get('messages', [])
            self.metadata = conversation_data.get('metadata', {})
            
            logger.info(f"Conversation loaded from: {filepath}")
            logger.info(f"Loaded {len(self.messages)} messages")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load conversation: {e}")
            return False
    
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
