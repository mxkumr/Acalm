import os
import time
from pathlib import Path

import chromadb
from httpx import ReadTimeout
from llama_index.core import Document, StorageContext, VectorStoreIndex, Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore
from pypdf import PdfReader


LLM_MODEL = "qwen3:4b"
EMBED_MODEL = "nomic-embed-text"

PAPERS_DIR = "papers"
CHROMA_DIR = "data/embeddings/chroma"
COLLECTION_NAME = "academic_papers"

CHUNK_SIZE = 600
CHUNK_OVERLAP = 80


def load_paper_documents():
    docs = []
    papers_path = Path(PAPERS_DIR)

    for pdf_path in sorted(papers_path.glob("*.pdf")):
        print(f"Reading PDF: {pdf_path.name}")
        reader = PdfReader(str(pdf_path))

        for page_num, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()

            if len(text) < 80:
                continue

            docs.append(
                Document(
                    text=text,
                    metadata={
                        "file_name": pdf_path.name,
                        "page_label": str(page_num),
                    },
                )
            )

    return docs


def build_or_load_index(vector_store, chroma_collection):
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    existing_count = chroma_collection.count()

    if existing_count > 0:
        print(f"Using existing Chroma index with {existing_count} vectors.")
        return VectorStoreIndex.from_vector_store(vector_store=vector_store)

    print("No vectors found. Building index from documents...")

    load_start = time.perf_counter()
    documents = load_paper_documents()
    print(f"Loaded {len(documents)} extracted PDF pages in {time.perf_counter() - load_start:.2f}s.")

    if not documents:
        raise RuntimeError(
            "No readable PDF text found in papers/. If your PDF is scanned, run OCR first."
        )

    parser = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    split_start = time.perf_counter()
    nodes = parser.get_nodes_from_documents(documents)
    print(f"Split into {len(nodes)} chunks in {time.perf_counter() - split_start:.2f}s.")

    index_start = time.perf_counter()
    index = VectorStoreIndex(
        nodes=nodes,
        storage_context=storage_context,
    )
    print(f"Indexed chunks in {time.perf_counter() - index_start:.2f}s.")

    return index


def main():
    os.makedirs(CHROMA_DIR, exist_ok=True)

    Settings.llm = Ollama(
        model=LLM_MODEL,
        request_timeout=900.0,
    )
    Settings.embed_model = OllamaEmbedding(model_name=EMBED_MODEL)

    print("Preparing ChromaDB index...")
    setup_start = time.perf_counter()

    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

    if os.getenv("RESET_CHROMA", "0") == "1":
        try:
            chroma_client.delete_collection(COLLECTION_NAME)
            print("Deleted existing Chroma collection for a clean rebuild.")
        except Exception:
            print("No existing Chroma collection to delete.")

    chroma_collection = chroma_client.get_or_create_collection(COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

    print(f"Chroma setup took {time.perf_counter() - setup_start:.2f}s.")

    index = build_or_load_index(vector_store, chroma_collection)

    query_engine = index.as_query_engine(
        similarity_top_k=2,
        response_mode="compact",
    )

    question = (
        "What types of eye-tracking data are collected by VR devices?"
    )

    print("\nQuestion:")
    print(question)

    try:
        query_start = time.perf_counter()
        response = query_engine.query(question)
        print(f"\nQuery completed in {time.perf_counter() - query_start:.2f}s.")
    except ReadTimeout:
        print("\nQuery timed out while waiting for Ollama response.")
        print("Try a smaller model or reduce retrieved context/chunk size.")
        return

    print("\nRetrieved chunks:")
    for i, source_node in enumerate(response.source_nodes, start=1):
        print(f"\nChunk {i}")
        print(source_node.node.text[:800])

    print("\nAnswer:")
    print(response)

    print("\nSources used:")
    for i, source_node in enumerate(response.source_nodes, start=1):
        metadata = source_node.node.metadata
        filename = metadata.get("file_name", "unknown file")
        page = metadata.get("page_label", "unknown page")
        score = source_node.score

        print(f"\nSource {i}")
        print(f"File: {filename}")
        print(f"Page: {page}")
        print(f"Score: {score}")
        print("Text preview:")
        print(source_node.node.text[:500])


if __name__ == "__main__":
    main()