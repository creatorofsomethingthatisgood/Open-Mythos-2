"""
Web UI - Gradio-based web interface
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional
from pathlib import Path

try:
    import gradio as gr
    GRADIO_AVAILABLE = True
except ImportError:
    GRADIO_AVAILABLE = False
    logging.warning("Gradio not available")

from engine.inference import InferenceEngine
from engine.prompt_manager import PromptManager
from engine.memory import ConversationMemory
from engine.rag import RAGPipeline
from engine.self_reflect import SelfReflector
from engine.context_budget import fit_chat_context
from engine.local_refs import build_local_file_context

logger = logging.getLogger(__name__)

ChatHistory = List[dict[str, Any]]


def _message_content(msg: Any) -> str:
    if isinstance(msg, dict):
        content = msg.get("content", "")
        return content if isinstance(content, str) else str(content)
    return str(msg)


def _sync_memory_from_chat_history(memory: ConversationMemory, history: Any) -> None:
    """Rebuild conversation memory from Gradio chatbot history."""
    memory.clear()
    if not history:
        return
    for item in history:
        if isinstance(item, dict):
            role = item.get("role")
            content = _message_content(item)
            if role in ("user", "assistant", "system") and content:
                memory.add_message(role, content)
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            user_msg, assistant_msg = item
            memory.add_message("user", str(user_msg))
            if assistant_msg:
                memory.add_message("assistant", str(assistant_msg))


def _append_chat_messages(
    history: Any, user_message: str, assistant_message: str
) -> ChatHistory:
    messages: ChatHistory = list(history or [])
    messages.append({"role": "user", "content": user_message})
    messages.append({"role": "assistant", "content": assistant_message})
    return messages


class WebUI:
    """Gradio web interface for Mythos Local"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize WebUI
        
        Args:
            config_path: Path to configuration file
        """
        if not GRADIO_AVAILABLE:
            raise RuntimeError("Gradio required. Install with: pip install gradio")
        
        self.config_path = config_path
        
        # Initialize components
        print("Initializing Mythos Local...")
        
        self.engine = InferenceEngine(config_path)
        self.prompt_manager = PromptManager(config_path)
        self.memory = ConversationMemory(config_path)
        self.reflector = SelfReflector(config_path)
        
        # RAG is optional
        self.rag = None
        self.rag_enabled = False
        try:
            self.rag = RAGPipeline(config_path)
        except:
            print("RAG not available (optional)")
        
        # Current settings
        self.current_temp = 0.7
        self.current_top_p = 0.9
        self.current_top_k = 40
        self.current_max_tokens = 2048
        self.current_repeat_penalty = 1.1
        
        print("Initialization complete!")
    
    def chat(
        self,
        message: str,
        history: ChatHistory,
        system_prompt: str,
        temperature: float,
        top_p: float,
        top_k: int,
        max_tokens: int,
        repeat_penalty: float,
        use_reflection: bool,
        use_rag: bool
    ) -> tuple[ChatHistory, str]:
        """
        Handle chat interaction
        
        Args:
            message: User message
            history: Chat history
            system_prompt: System prompt
            temperature: Sampling temperature
            top_p: Nucleus sampling
            top_k: Top-k sampling
            max_tokens: Max tokens to generate
            repeat_penalty: Repetition penalty
            use_reflection: Enable self-reflection
            use_rag: Enable RAG
            
        Returns:
            Tuple of (updated_history, status_message)
        """
        if not message.strip():
            return history, "Please enter a message"
        
        try:
            # Update system prompt
            self.prompt_manager.set_prompt(system_prompt)
            
            _sync_memory_from_chat_history(self.memory, history)
            
            # Add current message
            self.memory.add_message("user", message)
            
            # Get RAG context if enabled
            rag_context = ""
            if use_rag and self.rag:
                rag_context = self.rag.get_context(message)

            local_context, local_notices = build_local_file_context(
                message, self.engine.config
            )
            
            # Prepare prompt
            max_turns = 10
            if use_rag and self.rag:
                max_turns = self.rag.max_history_turns
            messages = self.memory.get_recent_context(max_turns=max_turns)

            sys_prompt = system_prompt
            extra_context = "\n\n".join(
                part for part in (rag_context, local_context) if part
            )
            if extra_context:
                sys_prompt = self.prompt_manager.format_with_context(extra_context)

            reserve = self.engine.config.get("context", {}).get(
                "reserve_tokens",
                self.engine.config.get("generation", {}).get("max_tokens", 2048),
            )
            messages, sys_prompt, _ = fit_chat_context(
                self.engine, messages, sys_prompt, reserve_tokens=reserve
            )

            prompt = self.engine.format_chat_prompt(messages, sys_prompt)
            
            # Generate response
            response = self.engine.generate(
                prompt,
                max_tokens=int(max_tokens),
                temperature=float(temperature),
                top_p=float(top_p),
                top_k=int(top_k),
                repeat_penalty=float(repeat_penalty),
                stream=False
            )
            
            # Apply reflection if enabled
            if use_reflection:
                response = self.reflector.reflect(
                    self.engine,
                    message,
                    response,
                    max_tokens=int(max_tokens),
                    temperature=float(temperature)
                )
            
            # Add to memory
            self.memory.add_message("assistant", response)
            
            history = _append_chat_messages(history, message, response)

            status = f"✓ Generated {len(response.split())} words"
            if use_reflection:
                status += " (with reflection)"
            if local_notices:
                status += " | " + "; ".join(local_notices[:3])
            
            return history, status
            
        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            return history, f"Error: {str(e)}"
    
    def upload_rag_document(self, file) -> str:
        """
        Upload and index a document for RAG
        
        Args:
            file: Uploaded file object
            
        Returns:
            Status message
        """
        if not self.rag:
            return "RAG not available"
        
        if file is None:
            return "No file uploaded"
        
        try:
            # Get file path
            filepath = Path(file.name)
            
            # Index document
            self.rag.index_document(filepath)
            
            stats = self.rag.get_stats()
            return f"✓ Document indexed. Total chunks: {stats['total_chunks']}"
            
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return f"Error: {str(e)}"
    
    def clear_conversation(self, history):
        """Clear conversation history"""
        self.memory.clear()
        return [], "Conversation cleared"
    
    def save_conversation(self, history) -> str:
        """Save conversation to file"""
        try:
            _sync_memory_from_chat_history(self.memory, history)
            filepath = self.memory.save()
            return f"✓ Saved to: {filepath}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def export_conversation(self, history) -> str:
        """Export conversation as text"""
        try:
            _sync_memory_from_chat_history(self.memory, history)
            text = self.memory.export_text()
            return text
        except Exception as e:
            return f"Error: {str(e)}"
    
    def create_interface(self) -> gr.Blocks:
        """
        Create Gradio interface
        
        Returns:
            Gradio Blocks interface
        """
        with gr.Blocks(title="Mythos Local") as demo:
            gr.Markdown("""
            # 🌟 Mythos Local
            ### High-Quality Local Language Model
            """)
            
            with gr.Row():
                with gr.Column(scale=3):
                    # Chat interface
                    chatbot = gr.Chatbot(
                        label="Conversation",
                        height=500,
                        buttons=["copy"],
                    )
                    
                    with gr.Row():
                        msg = gr.Textbox(
                            label="Message",
                            placeholder="Type your message here...",
                            lines=3,
                            scale=4
                        )
                        submit = gr.Button("Send", variant="primary", scale=1)
                    
                    status = gr.Textbox(label="Status", interactive=False)
                    
                    with gr.Row():
                        clear_btn = gr.Button("Clear")
                        save_btn = gr.Button("Save")
                        export_btn = gr.Button("Export")
                
                with gr.Column(scale=1):
                    # Settings sidebar
                    gr.Markdown("### Settings")
                    
                    system_prompt = gr.Textbox(
                        label="System Prompt",
                        value=self.prompt_manager.get_prompt(),
                        lines=6
                    )
                    
                    temperature = gr.Slider(
                        minimum=0.0,
                        maximum=2.0,
                        value=0.7,
                        step=0.1,
                        label="Temperature"
                    )
                    
                    top_p = gr.Slider(
                        minimum=0.0,
                        maximum=1.0,
                        value=0.9,
                        step=0.05,
                        label="Top P"
                    )
                    
                    top_k = gr.Slider(
                        minimum=0,
                        maximum=100,
                        value=40,
                        step=1,
                        label="Top K"
                    )
                    
                    max_tokens = gr.Slider(
                        minimum=256,
                        maximum=4096,
                        value=2048,
                        step=256,
                        label="Max Tokens"
                    )
                    
                    repeat_penalty = gr.Slider(
                        minimum=1.0,
                        maximum=2.0,
                        value=1.1,
                        step=0.1,
                        label="Repeat Penalty"
                    )
                    
                    use_reflection = gr.Checkbox(
                        label="Self-Reflection (slower, higher quality)",
                        value=False
                    )
                    
                    use_rag = gr.Checkbox(
                        label="RAG (Retrieval-Augmented Generation)",
                        value=False
                    )
                    
                    if self.rag:
                        gr.Markdown("### RAG Documents")
                        file_upload = gr.File(
                            label="Upload Document",
                            file_types=[".txt", ".md", ".pdf", ".py", ".json"]
                        )
                        upload_status = gr.Textbox(label="Upload Status", interactive=False)
                        
                        file_upload.change(
                            fn=self.upload_rag_document,
                            inputs=[file_upload],
                            outputs=[upload_status]
                        )
                    
                    gr.Markdown(f"**Model:** {self.engine.model_path.name}")
            
            # Export output
            export_output = gr.Textbox(
                label="Exported Conversation",
                lines=20,
                visible=False
            )
            
            # Event handlers
            submit_event = submit.click(
                fn=self.chat,
                inputs=[
                    msg,
                    chatbot,
                    system_prompt,
                    temperature,
                    top_p,
                    top_k,
                    max_tokens,
                    repeat_penalty,
                    use_reflection,
                    use_rag
                ],
                outputs=[chatbot, status]
            )
            
            msg.submit(
                fn=self.chat,
                inputs=[
                    msg,
                    chatbot,
                    system_prompt,
                    temperature,
                    top_p,
                    top_k,
                    max_tokens,
                    repeat_penalty,
                    use_reflection,
                    use_rag
                ],
                outputs=[chatbot, status]
            )
            
            # Clear message after send
            submit.click(lambda: "", None, msg)
            msg.submit(lambda: "", None, msg)
            
            clear_btn.click(
                fn=self.clear_conversation,
                inputs=[chatbot],
                outputs=[chatbot, status]
            )
            
            save_btn.click(
                fn=self.save_conversation,
                inputs=[chatbot],
                outputs=[status]
            )
            
            def show_export(history):
                text = self.export_conversation(history)
                return {
                    export_output: gr.update(value=text, visible=True)
                }
            
            export_btn.click(
                fn=show_export,
                inputs=[chatbot],
                outputs=[export_output]
            )
        
        return demo
    
    def launch(self, share: bool = False, port: int = 7860):
        """
        Launch the web interface
        
        Args:
            share: Create public link
            port: Port to run on
        """
        demo = self.create_interface()
        demo.launch(
            share=share,
            server_port=port,
            server_name="0.0.0.0",
            theme=gr.themes.Soft(),
        )


def run_web_ui(config_path: str = "config.yaml", share: bool = False, port: int = 7860):
    """
    Run the web UI
    
    Args:
        config_path: Path to configuration file
        share: Create public Gradio link
        port: Port to run on
    """
    ui = WebUI(config_path)
    ui.launch(share=share, port=port)
