"""
RAG Pipeline - Retrieval-Augmented Generation with ChromaDB
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import yaml

from engine.hf_cache import (
    configure_hf_cache,
    load_sentence_transformer,
    quiet_hf_loggers,
)
from engine.context_budget import truncate_text

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logging.warning("ChromaDB not available")

try:
    import sentence_transformers  # noqa: F401
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logging.warning("sentence-transformers not available")

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    logging.warning("PyPDF2 not available")

logger = logging.getLogger(__name__)


class RAGPipeline:
    """Retrieval-Augmented Generation pipeline"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize RAG pipeline
        
        Args:
            config_path: Path to configuration file
        """
        if not CHROMADB_AVAILABLE or not SENTENCE_TRANSFORMERS_AVAILABLE:
            self.available = False
            logger.info("RAG disabled: ChromaDB and sentence-transformers not installed")
            return
        
        self.available = True
        self.config_path = Path(config_path).resolve()
        self.project_root = self.config_path.parent
        self.config = self._load_config()
        
        # RAG configuration
        rag_config = self.config.get('rag', {})
        docs_dir = Path(rag_config.get('docs_dir', 'rag_docs'))
        self.docs_dir = docs_dir if docs_dir.is_absolute() else self.project_root / docs_dir
        
        self.chunk_size = rag_config.get('chunk_size', 500)
        self.chunk_overlap = rag_config.get('chunk_overlap', 50)
        self.top_k = rag_config.get('top_k', 3)
        self.max_context_chars = rag_config.get('max_context_chars', 20000)
        self.max_history_turns = rag_config.get('max_history_turns', 6)
        self.clear_before_index = rag_config.get('clear_before_index', True)
        self.max_file_bytes = int(rag_config.get('max_file_bytes', 2 * 1024 * 1024))
        self.exclude_dir_names = set(rag_config.get('exclude_dirs', [
            '.git', 'node_modules', '__pycache__', '.pytest_cache',
            'venv', '.venv', 'dist', 'build', '.next', 'coverage',
            'chroma_db', 'models', '.mypy_cache', '.tox', 'htmlcov',
        ]))
        self.extensions = rag_config.get('extensions', [
            '.txt', '.md', '.pdf', '.py', '.json', '.yaml', '.yml',
            '.ts', '.tsx', '.js', '.jsx', '.sql', '.sh', '.toml',
            '.ini', '.cfg', '.env.example', '.graphql', '.prisma',
            '.html', '.css', '.scss', '.xml', '.csv',
        ])
        
        # Hugging Face: project-local cache + quiet logs (avoids ~/.cache permission errors)
        hf_cache_dir = rag_config.get('hf_cache_dir', '.cache/huggingface')
        self.hf_cache_path = configure_hf_cache(self.project_root, hf_cache_dir)
        quiet_hf_loggers()

        embedding_model_name = rag_config.get(
            'embedding_model', 'sentence-transformers/all-MiniLM-L6-v2'
        )
        prefer_offline = rag_config.get('embedding_local_only', True)
        self.embedding_model = load_sentence_transformer(
            embedding_model_name,
            self.hf_cache_path,
            prefer_offline=prefer_offline,
        )
        
        # Persistent disk store (Client() alone is in-memory in Chroma 1.x)
        persist_dir = Path(rag_config.get('persist_dir', 'chroma_db'))
        self.persist_dir = (
            persist_dir if persist_dir.is_absolute() else self.project_root / persist_dir
        )
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"},
        )
        
        logger.info(
            "RAG pipeline initialized (persist=%s, docs=%s, chunks=%d)",
            self.persist_dir,
            self.docs_dir,
            self.collection.count(),
        )
    
    def _load_config(self) -> Dict:
        """Load configuration from YAML"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    def load_document(self, filepath: Path) -> str:
        """
        Load document content based on file type
        
        Args:
            filepath: Path to document
            
        Returns:
            Document text
        """
        suffix = filepath.suffix.lower()
        
        try:
            if suffix == '.pdf':
                return self._load_pdf(filepath)
            elif suffix in self.extensions and suffix != '.pdf':
                return self._load_text(filepath)
            else:
                logger.warning(f"Unsupported file type: {suffix}")
                return ""
        except Exception as e:
            logger.error(f"Failed to load document {filepath}: {e}")
            return ""
    
    def _load_text(self, filepath: Path) -> str:
        """Load plain text file"""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read text file: {e}")
            return ""
    
    def _load_pdf(self, filepath: Path) -> str:
        """Load PDF file"""
        if not PYPDF2_AVAILABLE:
            logger.warning("PyPDF2 not available, skipping PDF")
            return ""
        
        try:
            text = []
            with open(filepath, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                for page in pdf_reader.pages:
                    text.append(page.extract_text())
            return "\n".join(text)
        except Exception as e:
            logger.error(f"Failed to read PDF: {e}")
            return ""
    
    def chunk_text(self, text: str, metadata: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Split text into chunks
        
        Args:
            text: Document text
            metadata: Optional metadata to attach to chunks
            
        Returns:
            List of chunk dictionaries
        """
        # Simple word-based chunking
        words = text.split()
        if not words:
            return []

        step = max(1, self.chunk_size - self.chunk_overlap)
        chunks = []

        for i in range(0, len(words), step):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = " ".join(chunk_words)
            
            chunk_data = {
                'text': chunk_text,
                'metadata': metadata or {},
                'chunk_index': len(chunks)
            }
            chunks.append(chunk_data)
        
        if chunks:
            logger.debug(f"Created {len(chunks)} chunks from text")
        return chunks
    
    def index_document(self, filepath: Path):
        """
        Index a document into the vector store
        
        Args:
            filepath: Path to document
        """
        logger.debug(f"Indexing document: {filepath}")
        
        # Load document
        text = self.load_document(filepath)
        if not text or not text.strip():
            logger.debug(f"Skipping empty file: {filepath}")
            return
        
        # Create chunks
        try:
            rel_source = str(filepath.resolve().relative_to(self.docs_dir.resolve()))
        except ValueError:
            rel_source = str(filepath)
        metadata = {
            'source': rel_source,
            'filename': filepath.name,
            'type': filepath.suffix,
        }
        chunks = self.chunk_text(text, metadata)
        if not chunks:
            logger.debug(f"Skipping file with no indexable content: {filepath}")
            return

        # Generate embeddings
        chunk_texts = [chunk['text'] for chunk in chunks]
        if not any(t.strip() for t in chunk_texts):
            logger.debug(f"Skipping file with only whitespace chunks: {filepath}")
            return

        embeddings = self.embedding_model.encode(chunk_texts).tolist()
        
        # Stable IDs from path (avoids collisions across nested dirs)
        doc_id = self._doc_id_for_path(filepath)
        ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        
        # Add to collection
        metadatas = [chunk['metadata'] for chunk in chunks]
        
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunk_texts,
            metadatas=metadatas
        )
        
        logger.debug(f"Indexed {len(chunks)} chunks from {filepath.name}")
    
    def _doc_id_for_path(self, filepath: Path) -> str:
        """Unique collection id from path relative to docs_dir when possible."""
        try:
            rel = filepath.resolve().relative_to(self.docs_dir.resolve())
        except ValueError:
            rel = filepath
        return str(rel).replace('/', '_').replace('\\', '_').replace(' ', '_')

    def _should_skip_path(self, filepath: Path) -> bool:
        """Skip hidden files, excluded dirs, and oversized files."""
        parts = set(filepath.parts)
        if parts & self.exclude_dir_names:
            return True
        if filepath.name.startswith('.') and filepath.suffix not in ('.env.example',):
            return True
        try:
            if filepath.stat().st_size > self.max_file_bytes:
                logger.warning(f"Skipping large file ({filepath.stat().st_size} bytes): {filepath}")
                return True
        except OSError:
            return True
        return False

    def resolve_docs_path(self, path: Optional[str] = None) -> Path:
        """
        Resolve a docs directory from config default or an override path.

        Relative paths are resolved against the project root (config parent).
        """
        if path is None or not str(path).strip():
            return self.docs_dir.resolve()
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.project_root / candidate
        return candidate.resolve()

    def iter_indexable_files(self, directory: Path):
        """Yield all indexable files under directory recursively."""
        if not directory.exists():
            logger.error(f"Directory does not exist: {directory}")
            return
        for ext in self.extensions:
            for filepath in directory.rglob(f"*{ext}"):
                if filepath.is_file() and not self._should_skip_path(filepath):
                    yield filepath

    def explore_directory(self, path: Optional[str] = None) -> Dict[str, Any]:
        """
        Summarize which files would be indexed under a directory (no embedding).

        Args:
            path: Directory to scan (config rag.docs_dir if omitted)

        Returns:
            Summary dict with counts, sizes, and sample paths
        """
        directory = self.resolve_docs_path(path)
        if not directory.exists():
            return {
                "directory": str(directory),
                "exists": False,
                "file_count": 0,
                "total_bytes": 0,
                "by_extension": {},
                "sample_files": [],
                "supported_extensions": sorted(self.extensions),
                "exclude_dirs": sorted(self.exclude_dir_names),
            }

        files = list(self.iter_indexable_files(directory))
        by_extension: Dict[str, int] = {}
        total_bytes = 0
        for filepath in files:
            ext = filepath.suffix.lower() or "(no extension)"
            by_extension[ext] = by_extension.get(ext, 0) + 1
            try:
                total_bytes += filepath.stat().st_size
            except OSError:
                pass

        sample_files = []
        for filepath in files[:25]:
            try:
                sample_files.append(str(filepath.relative_to(directory)))
            except ValueError:
                sample_files.append(str(filepath))

        return {
            "directory": str(directory),
            "exists": True,
            "file_count": len(files),
            "total_bytes": total_bytes,
            "by_extension": dict(sorted(by_extension.items())),
            "sample_files": sample_files,
            "supported_extensions": sorted(self.extensions),
            "exclude_dirs": sorted(self.exclude_dir_names),
        }

    def index_directory(
        self,
        directory: Optional[Path] = None,
        clear: Optional[bool] = None,
        path: Optional[str] = None,
    ):
        """
        Recursively index all supported documents under a directory.

        Args:
            directory: Directory to index (uses docs_dir if None)
            clear: Clear existing index first (uses config clear_before_index if None)
            path: Optional path string override (resolved via resolve_docs_path)
        """
        if not getattr(self, "available", True):
            raise RuntimeError("ChromaDB and sentence-transformers required. Install with: pip install -e \".[rag]\"")
        if path is not None:
            directory = self.resolve_docs_path(path)
            self.docs_dir = directory
        elif directory is None:
            directory = self.docs_dir
        directory = Path(directory)

        if clear is None:
            clear = self.clear_before_index
        if clear:
            self.clear_index()

        logger.info(f"Indexing directory (recursive): {directory.resolve()}")

        indexed_count = 0
        skipped_count = 0
        files = list(self.iter_indexable_files(directory))
        total_files = len(files)
        logger.info(f"Found {total_files} files to index under {directory}")

        for i, filepath in enumerate(files, 1):
            before = self.collection.count()
            self.index_document(filepath)
            after = self.collection.count()
            if after > before:
                indexed_count += 1
            else:
                skipped_count += 1
            if i % 50 == 0 or i == total_files:
                logger.info(
                    "Progress: %d/%d files, %d chunks in index",
                    i,
                    total_files,
                    self.collection.count(),
                )

        logger.info(
            "Indexed %d documents (%d empty/unsupported skipped), %d total chunks",
            indexed_count,
            skipped_count,
            self.collection.count(),
        )
    
    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retrieve relevant chunks for a query
        
        Args:
            query: Query text
            top_k: Number of chunks to retrieve (uses config default if None)
            
        Returns:
            List of relevant chunks with metadata
        """
        if top_k is None:
            top_k = self.top_k
        
        # Generate query embedding
        query_embedding = self.embedding_model.encode([query])[0].tolist()
        
        # Query collection
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        # Format results
        chunks = []
        if results['documents']:
            for i, doc in enumerate(results['documents'][0]):
                chunk = {
                    'text': doc,
                    'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                    'distance': results['distances'][0][i] if results['distances'] else None
                }
                chunks.append(chunk)
        
        logger.info(f"Retrieved {len(chunks)} chunks for query")
        return chunks
    
    def get_context(self, query: str, top_k: Optional[int] = None) -> str:
        """
        Get formatted context for a query
        
        Args:
            query: Query text
            top_k: Number of chunks to retrieve
            
        Returns:
            Formatted context string
        """
        chunks = self.retrieve(query, top_k)
        
        if not chunks:
            return ""
        
        context_parts = []
        context_parts.append("RELEVANT INFORMATION FROM DOCUMENTS:\n")
        
        for i, chunk in enumerate(chunks, 1):
            source = chunk['metadata'].get('filename', 'Unknown')
            text = chunk['text']
            context_parts.append(f"\n[Source {i}: {source}]")
            context_parts.append(text)
            context_parts.append("")
        
        context = "\n".join(context_parts)
        if len(context) > self.max_context_chars:
            context = truncate_text(context, self.max_context_chars)
            logger.info(
                "RAG context capped at %d chars (config rag.max_context_chars)",
                self.max_context_chars,
            )
        return context
    
    def clear_index(self):
        """Clear all indexed documents"""
        if not getattr(self, "available", True):
            return
        # Delete and recreate collection
        self.client.delete_collection(name="documents")
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"}
        )
        logger.info("Document index cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about indexed documents
        
        Returns:
            Statistics dictionary
        """
        count = self.collection.count()
        return {
            'total_chunks': count,
            'docs_directory': str(self.docs_dir),
            'persist_directory': str(self.persist_dir),
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
        }
