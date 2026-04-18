from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingModel(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError("Install sentence-transformers: pip install sentence-transformers") from e
        self._model = SentenceTransformer(model_name)
        self._model_name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, show_progress_bar=False).tolist()

    def __str__(self) -> str:
        return f"SentenceTransformerEmbedder/{self._model_name}"


class OpenAIEmbedder:
    def __init__(self, model_name: str = "text-embedding-3-small", api_key: str = ""):
        try:
            import openai
        except ImportError as e:
            raise ImportError("Install openai: pip install openai") from e
        import openai as _openai
        self._client = _openai.OpenAI(api_key=api_key)
        self._model_name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(input=texts, model=self._model_name)
        return [item.embedding for item in response.data]

    def __str__(self) -> str:
        return f"OpenAIEmbedder/{self._model_name}"


class BedrockEmbedder:
    def __init__(self, model_id: str = "amazon.titan-embed-text-v2:0", region: str = "us-east-1"):
        try:
            import boto3
            import json
        except ImportError as e:
            raise ImportError("Install boto3: pip install boto3") from e
        import boto3 as _boto3
        import json as _json
        self._client = _boto3.client("bedrock-runtime", region_name=region)
        self._model_id = model_id
        self._json = _json

    def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            body = self._json.dumps({"inputText": text})
            response = self._client.invoke_model(modelId=self._model_id, body=body)
            parsed = self._json.loads(response["body"].read())
            results.append(parsed["embedding"])
        return results

    def __str__(self) -> str:
        return f"BedrockEmbedder/{self._model_id}"


class AzureOpenAIEmbedder:
    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str = "2024-02-01",
    ):
        try:
            import openai
        except ImportError as e:
            raise ImportError("Install openai: pip install openai") from e
        import openai as _openai
        self._client = _openai.AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        self._deployment = deployment

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(input=texts, model=self._deployment)
        return [item.embedding for item in response.data]

    def __str__(self) -> str:
        return f"AzureOpenAIEmbedder/{self._deployment}"


class VertexAIEmbedder:
    """Uses Google Cloud Vertex AI (Gecko or newer) for embeddings in GCP pipelines."""
    def __init__(self, model: str = "text-embedding-004", project: str | None = None, location: str | None = None):
        try:
            from vertexai.language_models import TextEmbeddingModel
            import vertexai
        except ImportError as e:
            raise ImportError("Install google-cloud-aiplatform: pip install google-cloud-aiplatform") from e

        if project or location:
            # Only strictly init if specified, otherwise uses environment defaults mapping via application default credentials.
            vertexai.init(project=project, location=location)
            
        self._client = TextEmbeddingModel.from_pretrained(model)
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Vertex AI SDK requires the text strings, and returns `TextEmbedding` objects which hold a `values` float list.
        # It handles batching natively up to 250 requests
        embeddings = self._client.get_embeddings(texts)
        return [emb.values for emb in embeddings]

    def __str__(self) -> str:
        return f"VertexAIEmbedder/{self._model}"
