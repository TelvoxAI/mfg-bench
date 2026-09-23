#!/usr/bin/env bash
# Deploy raw-corpus-mcp to Cloud Run, one service per mode (IND-982 Part I).
#
#   raw_corpus_mcp/deploy.sh keyword   # → raw-corpus-keyword
#   raw_corpus_mcp/deploy.sh hybrid    # → raw-corpus-hybrid (needs gold/vectors.{npy,json})
#
# Expects: the corpus at ./corpus (export --export-format json, or a copy of
# generated_data/sources), the secret raw-corpus-mcp-token in Secret Manager, and
# gcloud pointed at indax-495403. The service is public (--allow-unauthenticated): the
# bearer token is the lock, as the Claude MCP connector cannot present an IAM token.
set -euo pipefail
MODE="${1:?keyword|hybrid}"
PROJECT="${PROJECT:-indax-495403}"
REGION="${REGION:-us-central1}"
IMAGE="us-central1-docker.pkg.dev/${PROJECT}/mfg-bench/raw-corpus-mcp:${MODE}"
SERVICE="raw-corpus-${MODE}"

[ -d corpus ] || { echo "./corpus missing (copy generated_data/sources or the json export here)"; exit 1; }
if [ "$MODE" = hybrid ]; then
  mkdir -p corpus_vectors && cp gold/vectors.npy gold/vectors.json corpus_vectors/
fi

gcloud artifacts repositories describe mfg-bench --location "$REGION" --project "$PROJECT" >/dev/null 2>&1 \
  || gcloud artifacts repositories create mfg-bench --repository-format docker --location "$REGION" --project "$PROJECT"
gcloud builds submit --tag "$IMAGE" --project "$PROJECT" -f raw_corpus_mcp/Dockerfile .

ENV="MODE=${MODE}"
SECRETS="MCP_AUTH_TOKEN=raw-corpus-mcp-token:latest"
if [ "$MODE" = hybrid ]; then
  ENV="${ENV},VECTORS=/data/vectors/vectors,EMBED_MODEL=text-embedding-3-large"
  SECRETS="${SECRETS},OPENAI_API_KEY=OPENAI_API_KEY:latest"
fi
gcloud run deploy "$SERVICE" --image "$IMAGE" --region "$REGION" --project "$PROJECT" \
  --platform managed --allow-unauthenticated --memory 4Gi --cpu 2 --concurrency 20 \
  --min-instances 0 --max-instances 3 --timeout 120 \
  --set-env-vars "$ENV" --set-secrets "$SECRETS"
URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format='value(status.url)')
echo "MCP endpoint: ${URL}/mcp"
curl -s "${URL}/healthz"; echo
