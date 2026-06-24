import os

import chromadb
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext, Settings
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore


LLM_MODEL = "qwen3.5:9b"
EMBED_MODEL = "nomic-embed-text"

PAPERS_DIR = "papers"
CHROMA_DIR = "data/embeddings/chroma"
COLLECTION_NAME = "academic_papers"


def main():
    os.makedirs(CHROMA_DIR, exist_ok=True)

    Settings.llm = Ollama(model=LLM_MODEL, request_timeout=300.0)
    Settings.embed_model = OllamaEmbedding(model_name=EMBED_MODEL)

    print("Loading documents...")
    documents = SimpleDirectoryReader(PAPERS_DIR).load_data()
    print(f"Loaded {len(documents)} document chunks.")

    print("Creating ChromaDB index...")
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    chroma_collection = chroma_client.get_or_create_collection(COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
    )

    query_engine = index.as_query_engine(similarity_top_k=1)

    question = (
        "Using only the provided source, explain why methodology is important "
        "in thesis writing. Write one academic paragraph."
    )

    print("\nQuestion:")
    print(question)

    response = query_engine.query(question)

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