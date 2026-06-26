from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from qdrant_client import QdrantClient


DEFAULT_QDRANT_PATH = Path("data/embeddings/qdrant")
DEFAULT_COLLECTION = "papers_md"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_LLM_MODEL = "qwen3.5:9b"


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Retrieve top-k chunks from Qdrant for a question and answer using Ollama.",
	)
	parser.add_argument(
		"question",
		nargs="?",
		type=str,
		help="Question to search against the vector database. If omitted, you will be prompted.",
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


def deduplicate_results(results, top_k: int):
	"""Keep the highest-scoring unique chunks so repeated vectors do not dominate."""
	unique = []
	seen = set()

	for point in results:
		payload = point.payload or {}
		filename = str(payload.get("file_name", "unknown"))
		text = (payload.get("text") or "").strip()
		if not text:
			continue

		key = (filename, text)
		if key in seen:
			continue

		seen.add(key)
		unique.append(point)

		if len(unique) >= top_k:
			break

	return unique


def main() -> None:
	args = parse_args()

	question = (args.question or "").strip()
	if not question:
		question = input("Ask a question: ").strip()

	if not question:
		raise ValueError("Question cannot be empty.")

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
	query_vector = embed_model.get_text_embedding(question)

	candidate_results = client.query_points(
		collection_name=args.collection,
		query=query_vector,
		limit=max(args.top_k * 4, args.top_k),
		with_payload=True,
	).points

	results = deduplicate_results(candidate_results, args.top_k)

	if not results:
		print("No results found.")
		return

	print("Question:")
	print(question)
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
		"You are a retrieval-grounded assistant. Analyze the chunks first, then answer. "
		"Use ONLY the provided context; do not use outside knowledge. "
		"Cite chunk numbers in every evidence bullet and in the answer. "
		"If context is insufficient, respond exactly: "
		"I do not know based on the retrieved context.\n\n"
		"Output format:\n"
		"Analysis:\n"
		"- <evidence bullet with citation like [Chunk 2]>\n"
		"- <evidence bullet with citation>\n"
		"Answer:\n"
		"<final grounded answer with citations>\n\n"
		f"Question:\n{question}\n\n"
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
