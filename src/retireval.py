from __future__ import annotations

import argparse
from pathlib import Path

from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from qdrant_client import QdrantClient


DEFAULT_QDRANT_PATH = Path("data/embeddings/qdrant")
DEFAULT_COLLECTION = "papers_md"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_LLM_MODEL = "llama3.5:9b"


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Retrieve top-k chunks from Qdrant for a question and answer using Ollama.",
	)
	parser.add_argument(
		"question",
		type=str,
		help="Question to search against the vector database.",
	)
	parser.add_argument(
		"--top-k",
		type=int,
		default=3,
		help="Number of chunks to retrieve (default: 3)",
	)
	parser.add_argument(
		"--qdrant-path",
		type=Path,
		default=DEFAULT_QDRANT_PATH,
		help=f"Local Qdrant storage path (default: {DEFAULT_QDRANT_PATH})",
	)
	parser.add_argument(
		"--collection",
		type=str,
		default=DEFAULT_COLLECTION,
		help=f"Qdrant collection name (default: {DEFAULT_COLLECTION})",
	)
	parser.add_argument(
		"--embed-model",
		type=str,
		default=DEFAULT_EMBED_MODEL,
		help=f"Embedding model name (default: {DEFAULT_EMBED_MODEL})",
	)
	parser.add_argument(
		"--llm-model",
		type=str,
		default=DEFAULT_LLM_MODEL,
		help=f"Ollama model used for answer synthesis (default: {DEFAULT_LLM_MODEL})",
	)
	parser.add_argument(
		"--no-answer",
		action="store_true",
		help="Only retrieve and print chunks, skip answer synthesis.",
	)
	return parser.parse_args()


def build_context(results) -> str:
	context_blocks = []
	for idx, point in enumerate(results, start=1):
		payload = point.payload or {}
		filename = payload.get("file_name", "unknown")
		score = point.score
		text = (payload.get("text") or "").strip()

		context_blocks.append(
			f"Chunk {idx}\n"
			f"File: {filename}\n"
			f"Score: {score:.4f}\n"
			f"Text:\n{text}"
		)

	return "\n\n".join(context_blocks)


def main() -> None:
	args = parse_args()

	if args.top_k <= 0:
		raise ValueError("--top-k must be greater than 0")

	if not args.qdrant_path.exists():
		raise FileNotFoundError(
			f"Qdrant path not found: {args.qdrant_path}. Run vectorization first."
		)

	client = QdrantClient(path=str(args.qdrant_path))
	if not client.collection_exists(args.collection):
		raise RuntimeError(
			f"Collection '{args.collection}' does not exist. Run vectorization first."
		)

	embed_model = OllamaEmbedding(model_name=args.embed_model)
	query_vector = embed_model.get_text_embedding(args.question)

	results = client.query_points(
		collection_name=args.collection,
		query=query_vector,
		limit=args.top_k,
		with_payload=True,
	).points

	if not results:
		print("No results found.")
		return

	print("Question:")
	print(args.question)
	print(f"\nTop {len(results)} retrieved chunks:\n")

	for idx, point in enumerate(results, start=1):
		payload = point.payload or {}
		filename = payload.get("file_name", "unknown")
		score = point.score
		text = (payload.get("text") or "").strip()

		print(f"Chunk {idx}")
		print(f"File: {filename}")
		print(f"Score: {score:.4f}")
		print("Text preview:")
		print(text[:1000])
		print()

	if args.no_answer:
		return

	context = build_context(results)
	prompt = (
		"Use only the provided context to answer the question. "
		"If the context is insufficient, say that clearly.\n\n"
		f"Question:\n{args.question}\n\n"
		f"Context:\n{context}\n"
	)

	llm = Ollama(model=args.llm_model, request_timeout=300.0)

	try:
		answer = llm.complete(prompt)
		print("Answer:\n")
		print(answer.text.strip())
	except Exception as exc:
		print(f"Could not generate answer with model '{args.llm_model}': {exc}")
		print("Retrieved chunks above are still valid for manual review.")


if __name__ == "__main__":
	main()
