"""
RAG Pipeline - Retrieval-Augmented Generation with ChromaDB
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import yaml

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logging.warning("ChromaDB not available")

try:
    from sentence_transformers import SentenceTransformer
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
            raise RuntimeError("ChromaDB and sentence-transformers required for RAG")
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        # RAG configuration
        rag_config = self.config.get('rag', {})
        self.docs_dir = Path(rag_config.get('docs_dir', 'rag_docs'))
        self.docs_dir.mkdir(exist_ok=True)
        
        self.chunk_size = rag_config.get('chunk_size', 500)
        self.chunk_overlap = rag_config.get('chunk_overlap', 50)
        self.top_k = rag_config.get('top_k', 3)
        
        # Initialize embedding model
        embedding_model_name = rag_config.get('embedding_model', 'all-MiniLM-L6-v2')
        logger.info(f"Loading embedding model: {embedding_model_name}")
        self.embedding_model = SentenceTransformer(embedding_model_name)
        
        # Initialize ChromaDB
        persist_dir = rag_config.get('persist_dir', 'chroma_db')
        self.client = chromadb.Client(Settings(
            persist_directory=persist_dir,
            anonymized_telemetry=False
        ))
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"}
        )
        
        logger.info("RAG pipeline initialized")
    
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
            elif suffix in ['.txt', '.md', '.py', '.json', '.yaml', '.yml']:
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
        chunks = []
        
        for i in range(0, len(words), self.chunk_size - self.chunk_overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = " ".join(chunk_words)
            
            chunk_data = {
                'text': chunk_text,
                'metadata': metadata or {},
                'chunk_index': len(chunks)
            }
            chunks.append(chunk_data)
        
        logger.info(f"Created {len(chunks)} chunks from text")
        return chunks
    
    def index_document(self, filepath: Path):
        """
        Index a document into the vector store
        
        Args:
            filepath: Path to document
        """
        logger.info(f"Indexing document: {filepath}")
        
        # Load document
        text = self.load_document(filepath)
        if not text:
            logger.warning(f"No text extracted from {filepath}")
            return
        
        # Create chunks
        metadata = {
            'source': str(filepath),
            'filename': filepath.name,
            'type': filepath.suffix
        }
        chunks = self.chunk_text(text, metadata)
        
        # Generate embeddings
        chunk_texts = [chunk['text'] for chunk in chunks]
        embeddings = self.embedding_model.encode(chunk_texts).tolist()
        
        # Create IDs
        doc_id = filepath.stem
        ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        
        # Add to collection
        metadatas = [chunk['metadata'] for chunk in chunks]
        
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunk_texts,
            metadatas=metadatas
        )
        
        logger.info(f"Indexed {len(chunks)} chunks from {filepath.name}")
    
    def index_directory(self, directory: Optional[Path] = None):
        """
        Index all documents in a directory
        
        Args:
            directory: Directory to index (uses docs_dir if None)
        """
        if directory is None:
            directory = self.docs_dir
        
        logger.info(f"Indexing directory: {directory}")
        
        # Supported extensions
        extensions = ['.txt', '.md', '.pdf', '.py', '.json', '.yaml', '.yml']
        
        indexed_count = 0
        for ext in extensions:
            for filepath in directory.glob(f"*{ext}"):
                self.index_document(filepath)
                indexed_count += 1
        
        logger.info(f"Indexed {indexed_count} documents")
    
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
        
        return "\n".join(context_parts)
    
    def clear_index(self):
        """Clear all indexed documents"""
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
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap
        }
