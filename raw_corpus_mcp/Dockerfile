# raw-corpus-mcp — Cloud Run image. Build from the repo root:
#   gcloud builds submit --tag us-central1-docker.pkg.dev/indax-495403/mfg-bench/raw-corpus-mcp .
# The corpus (and, for hybrid, the vectors) are copied into the image so the server is
# self-contained; MODE and MCP_AUTH_TOKEN come from the Cloud Run service.
FROM python:3.12-slim
WORKDIR /app
COPY raw_corpus_mcp/requirements.txt /app/raw_corpus_mcp/requirements.txt
RUN pip install --no-cache-dir -r /app/raw_corpus_mcp/requirements.txt
COPY raw_corpus_mcp /app/raw_corpus_mcp
# corpus: a directory laid out as <source>/... JSON documents (export --export-format json)
COPY corpus /data/sources
ENV CORPUS_DIR=/data/sources PORT=8080
CMD ["python", "-m", "raw_corpus_mcp"]
