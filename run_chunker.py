import argparse
import sys

from chunker.chunker import run
from chunker.embedders import (
    AzureOpenAIEmbedder,
    BedrockEmbedder,
    EmbeddingModel,
    OpenAIEmbedder,
    SentenceTransformerEmbedder,
    VertexAIEmbedder,
)


def build_embedder(args: argparse.Namespace) -> EmbeddingModel:
    if args.embedder == "sentence-transformers":
        return SentenceTransformerEmbedder(args.model or "all-MiniLM-L6-v2")
    if args.embedder == "openai":
        return OpenAIEmbedder(args.model or "text-embedding-3-small", args.api_key or "")
    if args.embedder == "bedrock":
        return BedrockEmbedder(args.model or "amazon.titan-embed-text-v2:0", args.region or "us-east-1")
    if args.embedder == "azure":
        return AzureOpenAIEmbedder(
            endpoint=args.endpoint or "",
            api_key=args.api_key or "",
            deployment=args.deployment or "",
        )
    if args.embedder == "vertexai":
        return VertexAIEmbedder(
            model=args.model or "text-embedding-004",
            project=args.gcp_project,
            location=args.gcp_location,
        )
    print(f"Unknown embedder: {args.embedder}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Semantic chunker for earnings call transcripts"
    )
    parser.add_argument("--input", required=True, help="Directory containing .txt transcripts")
    parser.add_argument("--output", default="output/chunks", help="Output directory for JSON chunks")
    parser.add_argument(
        "--embedder",
        default="sentence-transformers",
        choices=["sentence-transformers", "openai", "bedrock", "azure", "vertexai"],
        help="Embedding backend to use",
    )
    parser.add_argument("--model", default=None, help="Model name or ID for the chosen embedder")
    parser.add_argument("--threshold", type=float, default=0.75, help="Cosine similarity threshold for topic boundaries")
    parser.add_argument("--min-sentences", type=int, default=3, help="Minimum sentences per chunk")
    parser.add_argument("--max-sentences", type=int, default=15, help="Maximum sentences per chunk")
    parser.add_argument("--max-tokens", type=int, default=400, help="Maximum tokens per chunk")
    parser.add_argument("--api-key", default=None, help="API key (OpenAI or Azure)")
    parser.add_argument("--region", default="us-east-1", help="AWS region (Bedrock)")
    parser.add_argument("--endpoint", default=None, help="Azure OpenAI endpoint URL")
    parser.add_argument("--deployment", default=None, help="Azure OpenAI deployment name")
    parser.add_argument("--gcp-project", default=None, help="GCP Project ID (for Vertex AI)")
    parser.add_argument("--gcp-location", default=None, help="GCP Location/Region (for Vertex AI)")

    args = parser.parse_args()
    embedder = build_embedder(args)

    run(
        input_dir=args.input,
        output_dir=args.output,
        embedder=embedder,
        threshold=args.threshold,
        min_sentences=args.min_sentences,
        max_sentences=args.max_sentences,
        max_tokens=args.max_tokens,
    )


if __name__ == "__main__":
    main()
