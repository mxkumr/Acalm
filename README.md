# Academic LLM Thesis Assistant

A local academic writing and literature review assistant using:

- Ollama
- Qwen local models
- Python
- RAG
- ChromaDB
- Academic papers and thesis materials

## Environment setup

Create a local `.env` file from `.env.example` and set your NVIDIA API key there:

```env
NVIDIA_API_KEY=your_api_key_here
```

The retrieval script loads `.env` automatically, so `src/retireval.py` can use the key without hardcoding it in source.

Main goals:
1. Read and understand collected academic papers.
2. Support literature review writing.
3. Suggest accurate citations from uploaded sources.
4. Improve academic flow and thesis-style writing.
5. Help the user learn from the literature.