"""
Mythos API Server - FastAPI backend for the web UI

Provides REST API endpoints that the Vercel-deployed frontend calls.
Also serves the Gradio UI at / for backward compatibility.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from engine.inference import InferenceEngine
from engine.prompt_manager import PromptManager
from engine.memory import ConversationMemory
from engine.rag import RAGPipeline
from engine.self_reflect import SelfReflector
from engine.context_budget import fit_chat_context
from engine.local_refs import build_local_file_context

logger = logging.getLogger(__name__)


# --- Request/Response models ---

class ChatRequest(BaseModel):
    message: str
    history: List[dict[str, Any]] = Field(default_factory=list)
    system_prompt: str = ""
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 2048
    repeat_penalty: float = 1.1
    use_reflection: bool = False
    use_rag: bool = False
    use_thinking: bool = True


class ExportRequest(BaseModel):
    history: List[dict[str, Any]] = Field(default_factory=list)


class SaveRequest(BaseModel):
    history: List[dict[str, Any]] = Field(default_factory=list)


# --- App ---

def create_app(config_path: str = "config.yaml") -> FastAPI:
    app = FastAPI(title="Mythos Local API", version="2.0.5")

    cors_origins = os.getenv("MYTHOS_CORS_ORIGINS", "").split(",")
    cors_origins = [o.strip() for o in cors_origins if o.strip()] or [
        "http://localhost:7860",
        "http://127.0.0.1:7860",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    # Initialize components on startup
    state: dict[str, Any] = {}

    @app.on_event("startup")  # deprecated: switch to lifespan handler when dropping Pydantic v1 compat
    async def startup():
        logger.info("Initializing Mythos Local API...")
        state["engine"] = InferenceEngine(config_path)
        state["prompt_manager"] = PromptManager(config_path)
        state["memory"] = ConversationMemory(config_path)
        state["reflector"] = SelfReflector(config_path)
        try:
            state["rag"] = RAGPipeline(config_path)
        except Exception:
            state["rag"] = None
            logger.info("RAG not available (optional)")
        logger.info("Mythos Local API ready")

    # --- API endpoints ---

    @app.post("/api/chat")
    async def chat(req: ChatRequest):
        if not req.message.strip():
            raise HTTPException(400, "Empty message")

        try:
            engine: InferenceEngine = state["engine"]
            pm: PromptManager = state["prompt_manager"]
            memory: ConversationMemory = state["memory"]
            reflector: SelfReflector = state["reflector"]

            # Rebuild memory from history
            memory.clear()
            for msg in req.history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role in ("user", "assistant", "system") and content:
                    memory.add_message(role, content)

            memory.add_message("user", req.message)

            # RAG context
            rag_context = ""
            if req.use_rag and state.get("rag"):
                rag_context = state["rag"].get_context(req.message)

            local_context, local_notices = build_local_file_context(
                req.message, engine.config
            )

            max_turns = 10
            if req.use_rag and state.get("rag"):
                max_turns = state["rag"].max_history_turns
            messages = memory.get_recent_context(max_turns=max_turns)

            sys_prompt = req.system_prompt
            extra_context = "\n\n".join(
                part for part in (rag_context, local_context) if part
            )
            if extra_context:
                sys_prompt = pm.format_with_context(extra_context)

            # Inject thinking instructions into system prompt when thinking mode is on
            if req.use_thinking:
                thinking_instruction = (
                    "\n\nBefore answering, reason step by step inside <thinking> tags, "
                    "then give your final answer after </thinking>. "
                    "Keep reasoning concise and avoid repetition."
                )
                sys_prompt = sys_prompt + thinking_instruction

            reserve = engine.config.get("context", {}).get(
                "reserve_tokens",
                engine.config.get("generation", {}).get("max_tokens", 2048),
            )
            messages, sys_prompt, _ = fit_chat_context(
                engine, messages, sys_prompt, reserve_tokens=reserve
            )

            prompt = engine.format_chat_prompt(messages, sys_prompt)

            response = engine.generate(
                prompt,
                max_tokens=int(req.max_tokens),
                temperature=float(req.temperature),
                top_p=float(req.top_p),
                top_k=int(req.top_k),
                repeat_penalty=float(req.repeat_penalty),
                stream=False,
            )

            # Extract thinking/reasoning from the response if thinking mode is on
            reasoning = None
            if req.use_thinking:
                reasoning, answer = reflector.extract_reasoning(response)
                if reasoning:
                    response = answer
                else:
                    reasoning = None

            if req.use_reflection:
                response = reflector.reflect(
                    engine,
                    req.message,
                    response,
                    max_tokens=int(req.max_tokens),
                    temperature=float(req.temperature),
                )

            memory.add_message("assistant", response)

            # Build assistant history entry with optional reasoning
            assistant_entry = {"role": "assistant", "content": response}
            if reasoning:
                assistant_entry["reasoning"] = reasoning

            new_history = list(req.history) + [
                {"role": "user", "content": req.message},
                assistant_entry,
            ]

            status = f"Generated {len(response.split())} words"
            if req.use_thinking and reasoning:
                status += f" (with thinking: {len(reasoning.split())} words)"
            if req.use_reflection:
                status += " (with reflection)"
            if local_notices:
                status += " | " + "; ".join(local_notices[:3])

            result = {"history": new_history, "status": status}
            if reasoning:
                result["reasoning"] = reasoning

            return result

        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            raise HTTPException(500, "Internal server error") from e

    @app.post("/api/clear")
    async def clear():
        memory: ConversationMemory = state["memory"]
        memory.clear()
        return {"status": "Conversation cleared"}

    @app.post("/api/export")
    async def export_conversation(req: ExportRequest):
        lines = []
        for msg in req.history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            label = "You" if role == "user" else "Mythos" if role == "assistant" else role
            lines.append(f"{label}: {content}")
        text = "\n\n---\n\n".join(lines)
        return PlainTextResponse(text)

    @app.post("/api/save")
    async def save_conversation(req: SaveRequest):
        try:
            memory: ConversationMemory = state["memory"]
            memory.clear()
            for msg in req.history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role in ("user", "assistant", "system") and content:
                    memory.add_message(role, content)
            filepath = memory.save()
            return {"status": f"Saved to: {filepath}"}
        except Exception as e:
            raise HTTPException(500, str(e)) from e

    @app.get("/api/prompt")
    async def get_prompt(name: str = "default"):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise HTTPException(400, "Invalid prompt name")
        prompts_dir = Path("prompts").resolve()
        prompt_file = (prompts_dir / f"{name}.txt").resolve()
        if not prompt_file.is_relative_to(prompts_dir):
            raise HTTPException(400, "Invalid prompt name")
        if prompt_file.exists():
            return PlainTextResponse(prompt_file.read_text())
        raise HTTPException(404, "Prompt not found")

    @app.get("/api/health")
    async def health():
        engine: InferenceEngine = state.get("engine")
        model_name = engine.model_path.name if engine and hasattr(engine, "model_path") else "unknown"
        return {
            "status": "ok",
            "model": model_name,
            "rag": state.get("rag") is not None,
        }

    @app.post("/api/rag-upload")
    async def rag_upload(file: UploadFile):
        """Upload a document to the RAG pipeline."""
        rag: Optional[RAGPipeline] = state.get("rag")
        if rag is None:
            raise HTTPException(400, "RAG pipeline is not enabled")

        # Validate filename
        filename = file.filename or "upload.txt"
        if "/" in filename or "\\" in filename:
            raise HTTPException(400, "Invalid filename")

        # Read content with size limit (10 MB)
        content = await file.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(400, "File too large (max 10 MB)")

        # Save to docs directory and index
        dest = rag.docs_dir / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(content)

        rag.index_document(dest)
        return f"Indexed {filename}"

    return app


def run_api_server(config_path: str = "config.yaml", port: int = 7860):
    """Run the API server (also compatible with the Vercel frontend)."""
    import uvicorn
    host = os.getenv("MYTHOS_API_HOST", "127.0.0.1")
    app = create_app(config_path)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import sys
    config = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 7860
    run_api_server(config, port)
