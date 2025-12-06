# Inventory Management (BigQuery) — Render deployment

## Files included
- app.py (Streamlit app)
- db_functions.py (BigQuery helpers)
- start.sh (startup script that writes service-account JSON from env var)
- Procfile
- requirements.txt
- .gitignore

## Deployment on Render
1. In Render, create a new Web Service from this repo.
2. Set the build command: `pip install -r requirements.txt`
3. Set the start command: `bash start.sh`
4. **Add environment variable** `GCP_SERVICE_ACCOUNT_JSON` with the **contents** of your JSON key (not the path). Alternatively set `GOOGLE_APPLICATION_CREDENTIALS` to a secret value with the path on the host (less common).
5. Ensure BigQuery API enabled and the service account has BigQuery permissions (BigQuery Data Viewer & BigQuery Job User and BigQuery Data Editor if you do inserts).

> **Do not commit** the JSON key to the repository.
