from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding

LLM_MODEL = "qwen3.5:9b"
EMBED_MODEL = "nomic-embed-text"

llm = Ollama(model=LLM_MODEL, request_timeout=120.0)
embed_model = OllamaEmbedding(model_name=EMBED_MODEL)

response = llm.complete("Write one sentence explaining what a literature review does in a thesis.")
print("\nLLM response:")
print(response)

embedding = embed_model.get_text_embedding("A literature review synthesizes prior research.")
print("\nEmbedding length:")
print(len(embedding))