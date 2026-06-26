from __future__ import annotations

import argparse
from pathlib import Path

from docling.document_converter import DocumentConverter


DEFAULT_PAPERS_DIR = Path("papers")
DEFAULT_OUTPUT_DIR = DEFAULT_PAPERS_DIR / "md"


def convert_pdf_to_markdown(
	converter: DocumentConverter,
	pdf_path: Path,
	output_path: Path,
) -> bool:
	"""Convert one PDF file to Markdown.

	Returns True when conversion succeeds, otherwise False.
	"""
	try:
		result = converter.convert(str(pdf_path))
		markdown = result.document.export_to_markdown()
		output_path.write_text(markdown, encoding="utf-8")
		return True
	except Exception as exc:
		print(f"Failed to convert {pdf_path.name}: {exc}")
		return False


def convert_all_papers(papers_dir: Path, output_dir: Path) -> None:
	output_dir.mkdir(parents=True, exist_ok=True)

	pdf_files = sorted(papers_dir.glob("*.pdf"))

	if not pdf_files:
		print(f"No PDF files found in {papers_dir}.")
		return

	converter = DocumentConverter()

	converted = 0
	failed = 0

	for pdf_path in pdf_files:
		output_path = output_dir / f"{pdf_path.stem}.md"
		print(f"Converting: {pdf_path.name} -> {output_path.name}")

		if convert_pdf_to_markdown(converter, pdf_path, output_path):
			converted += 1
		else:
			failed += 1

	print("\nDone.")
	print(f"Converted: {converted}")
	print(f"Failed: {failed}")
	print(f"Output directory: {output_dir}")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Convert PDFs in papers/ to Markdown files in papers/md using Docling.",
	)
	parser.add_argument(
		"--papers-dir",
		type=Path,
		default=DEFAULT_PAPERS_DIR,
		help=f"Directory containing PDF files (default: {DEFAULT_PAPERS_DIR})",
	)
	parser.add_argument(
		"--output-dir",
		type=Path,
		default=DEFAULT_OUTPUT_DIR,
		help=f"Directory to write Markdown files (default: {DEFAULT_OUTPUT_DIR})",
	)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	convert_all_papers(args.papers_dir, args.output_dir)


if __name__ == "__main__":
	main()
