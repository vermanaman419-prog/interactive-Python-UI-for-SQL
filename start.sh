#!/usr/bin/env bash
set -e

# If environment variable GCP_SERVICE_ACCOUNT_JSON exists (full JSON contents),
# write it to a file and set GOOGLE_APPLICATION_CREDENTIALS to that path.
if [ -n "$GCP_SERVICE_ACCOUNT_JSON" ]; then
  echo "Writing service account JSON to /tmp/service_account_key.json"
  printf '%s' "$GCP_SERVICE_ACCOUNT_JSON" > /tmp/service_account_key.json
  export GOOGLE_APPLICATION_CREDENTIALS="/tmp/service_account_key.json"
fi

# Start Streamlit on the port Render provides (default $PORT)
PORT=${PORT:-10000}
echo "Starting Streamlit on port $PORT"
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
