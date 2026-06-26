from __future__ import annotations

import argparse
import uuid
from pathlib import Path
from typing import Iterable, List, Sequence

from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.ollama import OllamaEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models


DEFAULT_MD_DIR = Path("papers/md")
DEFAULT_QDRANT_PATH = Path("data/embeddings/qdrant")
DEFAULT_COLLECTION = "papers_md"
DEFAULT_EMBED_MODEL = "nomic-embed-text"


def load_markdown_documents(md_dir: Path) -> List[Document]:
	docs: List[Document] = []

	for md_path in sorted(md_dir.glob("*.md")):
		text = md_path.read_text(encoding="utf-8").strip()
		if not text:
			continue

		docs.append(
			Document(
				text=text,
				metadata={
					"file_name": md_path.name,
					"source_path": str(md_path),
				},
			)
		)

	return docs


def chunk_documents(
	documents: Sequence[Document],
	chunk_size: int,
	chunk_overlap: int,
):
	parser = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
	return parser.get_nodes_from_documents(documents)


def batched(items: Sequence, batch_size: int) -> Iterable[Sequence]:
	for idx in range(0, len(items), batch_size):
		yield items[idx : idx + batch_size]


def build_points(nodes, embed_model: OllamaEmbedding):
	texts = [node.get_content() for node in nodes]
	embeddings = embed_model.get_text_embedding_batch(texts)

	points = []
	for node, vector in zip(nodes, embeddings):
		payload = dict(node.metadata)
		payload["text"] = node.get_content()

		points.append(
			models.PointStruct(
				id=str(uuid.uuid4()),
				vector=vector,
				payload=payload,
			)
		)

	return points


def ensure_collection(
	client: QdrantClient,
	collection_name: str,
	vector_size: int,
	recreate: bool,
) -> None:
	exists = client.collection_exists(collection_name)

	if exists and recreate:
		client.delete_collection(collection_name=collection_name)
		exists = False
		print(f"Deleted existing collection: {collection_name}")

	if not exists:
		client.create_collection(
			collection_name=collection_name,
			vectors_config=models.VectorParams(
				size=vector_size,
				distance=models.Distance.COSINE,
			),
		)
		print(f"Created collection: {collection_name}")
	else:
		print(f"Using existing collection: {collection_name}")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Vectorize Markdown files from papers/md into Qdrant using embeddings.",
	)
	parser.add_argument(
		"--md-dir",
		type=Path,
		default=DEFAULT_MD_DIR,
		help=f"Directory containing Markdown files (default: {DEFAULT_MD_DIR})",
	)
	parser.add_argument(
		"--qdrant-path",
		type=Path,
		default=DEFAULT_QDRANT_PATH,
		help=f"Persistent local Qdrant path (default: {DEFAULT_QDRANT_PATH})",
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
		help=f"Ollama embedding model name (default: {DEFAULT_EMBED_MODEL})",
	)
	parser.add_argument(
		"--chunk-size",
		type=int,
		default=600,
		help="Chunk size for splitting markdown text.",
	)
	parser.add_argument(
		"--chunk-overlap",
		type=int,
		default=80,
		help="Chunk overlap for splitting markdown text.",
	)
	parser.add_argument(
		"--batch-size",
		type=int,
		default=32,
		help="Batch size for embeddings and Qdrant upserts.",
	)
	parser.add_argument(
		"--recreate",
		action="store_true",
		help="Delete and recreate the collection before indexing.",
	)
	return parser.parse_args()


def main() -> None:
	args = parse_args()

	if not args.md_dir.exists():
		raise FileNotFoundError(f"Markdown directory not found: {args.md_dir}")

	args.qdrant_path.mkdir(parents=True, exist_ok=True)

	print(f"Loading Markdown files from {args.md_dir}...")
	documents = load_markdown_documents(args.md_dir)
	if not documents:
		raise RuntimeError(f"No Markdown files with text found in {args.md_dir}")

	print(f"Loaded {len(documents)} markdown documents.")
	nodes = chunk_documents(documents, args.chunk_size, args.chunk_overlap)
	if not nodes:
		raise RuntimeError("No chunks were created from markdown documents.")

	print(f"Created {len(nodes)} chunks.")

	embed_model = OllamaEmbedding(model_name=args.embed_model)
	client = QdrantClient(path=str(args.qdrant_path))

	sample_vector = embed_model.get_text_embedding(nodes[0].get_content())
	ensure_collection(
		client=client,
		collection_name=args.collection,
		vector_size=len(sample_vector),
		recreate=args.recreate,
	)

	print("Embedding chunks and upserting into Qdrant...")
	total_points = 0
	for batch in batched(nodes, args.batch_size):
		points = build_points(batch, embed_model)
		client.upsert(collection_name=args.collection, points=points, wait=True)
		total_points += len(points)
		print(f"Upserted {total_points}/{len(nodes)} chunks")

	print("\nVectorization complete.")
	print(f"Collection: {args.collection}")
	print(f"Qdrant path: {args.qdrant_path}")
	print(f"Points stored: {total_points}")


if __name__ == "__main__":
	main()
