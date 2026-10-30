# React + FastAPI

React and TypeScript frontend in `client/`, Python FastAPI backend in `server/`.
The frontend uses `/api` on the same origin locally and in production.

## Local setup (Windows PowerShell)

Use Node.js 24 and Python 3.12. From the repository root:

```powershell
npm install
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn server.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal at the repository root, start the frontend:

```powershell
npm run dev
```

Open http://localhost:5173 (or the URL Vite prints). The page shows the
document upload interface and your library. Stop each server with Ctrl+C.

If your Python environment is activated, `npm run dev:server` also starts
FastAPI. On macOS/Linux, create the environment with `python3 -m venv .venv`
and use `.venv/bin/python` instead of the Windows executable path.

## Check the connection

- Frontend: http://localhost:5173
- API greeting: http://127.0.0.1:8000/api/hello
- Health check: http://127.0.0.1:8000/api/health
- Interactive API docs: http://127.0.0.1:8000/api/docs
- Frontend proxy: http://localhost:5173/api/hello

```powershell
npm run build
npm run lint
```

## Vercel deployment

The active provider is local Ollama for embeddings and chat. FastAPI
extracts and chunks documents; Neon stores the files, chunks, and vectors.
Local defaults are `nomic-embed-text:latest` for embeddings and `llama3.2:latest`
for chat. Start Ollama before uploading or chatting. No AI Gateway key or
Vercel AI billing verification is required for this local mode.

The separate Vercel implementation remains in `server/gateway.py`. Its calls
are commented beside the active local calls in `server/processing.py` and
`server/chat.py`. To enable cloud mode later, switch both model selectors and
both calls together. Set `AI_GATEWAY_API_KEY` in the backend environment and
complete the Vercel team's billing verification. There is no automatic fallback.

Vercel functions cannot reach Ollama on your computer's localhost. Deploying
in local mode requires a separately hosted, securely reachable Ollama service
configured with `OLLAMA_BASE_URL` and optional `OLLAMA_API_KEY`.

Existing Ollama documents are immediately searchable again. If a document was
processed using a different embedding model, click **Create chunks** in the
library. Replacement is atomic and preserves old chunks if generation fails.

Push to your connected Git provider and deploy the repository root (`.`),
with the Vite framework preset. `vercel.json` configures the build command,
`client/dist` output, and API rewrites. No separate backend project is needed.
Set the backend-only `DATABASE_URL` environment variable to connect Neon.

`api/index.py` exports the FastAPI application. Vercel installs Python packages
from `requirements.txt`; `.python-version` selects Python 3.12. The same app
runs locally and on Vercel, with API documentation under `/api/docs`.

After deployment, verify `/api/health`, `/api/hello`, and `/api/docs` on the
production URL.

Documentation: [Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python).

## Neon PostgreSQL + pgvector

This workspace is linked to project `delicate-cloud-97171117`, branch
`production`, through the ignored `.neon` file. `neon.ts` preserves existing
branch settings and gives newly created non-default branches a seven-day TTL.
The Neon Codex plugin supplies both agent skills and the MCP server; no second
project-level MCP installation is needed.

To refresh this workspace's database variables after signing in:

```powershell
neon deploy
```

1. Create a Neon project (or add Neon through Vercel Storage / Marketplace).
   Choose a region close to your Vercel functions.
2. In Neon, click **Connect**, enable **Connection pooling**, and copy the
   PostgreSQL URL. Keep its SSL and channel-binding parameters.
3. Run `neon deploy` in the linked repository to pull `DATABASE_URL` (pooled)
   and `DATABASE_URL_UNPOOLED` (direct) into `.env.local` (or an existing `.env`).
   Alternatively, copy `.env.example` to `.env` and fill in both URLs manually.
   Both local environment files are ignored by Git. FastAPI loads `.env.local`
   before `.env`; variables injected by the host take precedence over both.
   Never put this secret in the frontend or a variable starting with `VITE_`.
4. Install the updated Python dependencies and initialize the database:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m server.init_db
```

Initialization enables pgvector and creates `documents` and `document_chunks`
in a transaction. It can be repeated without dropping existing tables or data.
The role used for this step must be allowed to create tables and extensions.
Run initialization explicitly, not at application startup or during each build.
Initialization uses `DATABASE_URL_UNPOOLED`; normal app requests use the pooled
`DATABASE_URL` connection.

Restart FastAPI and visit http://127.0.0.1:8000/api/health/db (or
http://localhost:5173/api/health/db through the frontend). A complete setup returns:

```json
{"status":"ok","database":"connected","pgvector":"enabled"}
```

Without a configured or reachable database, this endpoint returns HTTP 503;
the basic `/api/health` and `/api/hello` endpoints remain available.

For Vercel, add `DATABASE_URL` under **Settings → Environment Variables** for
the intended environments, then redeploy. Keep preview and production databases
separate when testing schema changes.

Chunks have source/page metadata, an embedding-model name, and a pgvector
column. The active embedding model is `nomic-embed-text:latest` in local Ollama.
Chat uses `llama3.2:latest`.

## Upload documents

Run the updated dependency install and `python -m server.init_db` before using
uploads. Initialization adds a nullable `file_content` column to `documents`
without changing existing rows. The two existing tables are retained.

Open the app, select or drop one PDF or UTF-8 TXT file (up to 4 MB), and click
**Upload document**. FastAPI extracts the text, creates overlapping chunks,
generates embeddings with local Ollama, and saves the source file and chunks together
in a database transaction. The document appears with a **Ready** status and
chunk count. Refreshing the page reloads the saved library.

- `POST /api/documents`: multipart upload, with the file under `file`.
- `GET /api/documents`: the latest 100 documents, without file bytes.
- `GET /api/documents/{id}/download`: download the original file.
- `POST /api/documents/{id}/process`: create chunks/embeddings for an existing
  upload. Reprocessing replaces that document's chunks atomically, so retries
  do not duplicate them and a failed attempt leaves its previous chunks intact.
- `GET /api/documents/{id}/chunks`: inspect chunk text, source pages, embedding
  model, and vector dimensions without downloading the raw vectors.

Original files remain stored as bytes in PostgreSQL.
Use object storage and direct uploads when adding larger files.
The 4 MB cap leaves room for multipart overhead under Vercel's function limits.
The current library is shared by all app visitors; add authentication and
document ownership before using it for private multi-user uploads.

## Active local mode with Ollama

Start the Ollama desktop app (or run `ollama serve` if no server is running).
Confirm that `ollama list` includes `nomic-embed-text:latest`. If needed:

```powershell
ollama pull nomic-embed-text
```

The defaults work without extra configuration or an external AI API key:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text:latest
OLLAMA_CHAT_MODEL=llama3.2:latest
```

Optional overrides belong in `.env.local` or `.env` on the backend. Restart
FastAPI after changing them. Confirm `ollama list` also includes `llama3.2:latest`
for chat; if needed, run `ollama pull llama3.2`.

PDFs are extracted page by page using pypdf; UTF-8 TXT files are decoded
directly. Chunks use up to 1,000 characters with a 150-character overlap,
preferring word boundaries and retaining PDF page numbers. Nomic document
inputs use `search_document: `; retrieval queries use
`search_query: ` through the same model. Ollama batches at most 16 chunks per
call. Embeddings are validated for count, dimensions, and finite values before
being saved in `document_chunks.embedding`.

For synchronous processing, documents are limited to 100 PDF pages, 200,000
extracted characters, and 250 chunks. Encrypted, unreadable, empty, and
image-only/scanned PDFs return actionable errors; OCR is not included. If
Ollama is unavailable, a new upload fails without saving a partial document.

For previously uploaded documents, click **Create chunks** in the library.
No new tables or schema migration are required.

## Chat with your documents

Open http://localhost:5173/chat, or click **Chat with documents** in the library.
Upload/process at least one document, select all documents or an individual
file, and ask a question. Enter sends; Shift+Enter adds a line break.

`POST /api/chat` accepts:

```json
{"message":"What are the main points?","history":[],"document_id":null}
```

`document_id` optionally scopes retrieval to one document UUID. `history` may
contain up to 12 user/assistant messages; client-supplied system roles are
rejected. The UI sends recent conversation context for follow-up questions.

FastAPI embeds the question using the configured embedding model, searches
pgvector by cosine distance with matching model/dimensions, and sends up to
four relevant passages to Ollama's chat model. Passages below cosine similarity
0.45 are omitted. Empty libraries or searches with no matching passages return
a helpful message without calling the chat model. This relevance threshold is
a heuristic and can need calibration for different document collections.

Answers include numbered citations and expandable source passages with PDF
page numbers or text chunk references. Source downloads return the original
file. Models are instructed to use only supplied passages and treat document
instructions as data; review sources to verify important answers.

Conversation history is kept in browser memory until refresh, **New chat**, or
document selection changes. It is not stored in the database. Existing tables
and uploaded files are retained. Local CPU generation may take a little time.

Cloud chat and embeddings share `AI_GATEWAY_API_KEY`. The preserved local
mode uses `OLLAMA_BASE_URL` and optional `OLLAMA_API_KEY`; localhost Ollama
is reachable only during local development.

Run backend checks with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s server/tests -v
```

Provider docs: [Neon pgvector](https://neon.com/docs/extensions/pgvector)
and [Neon connection pooling](https://neon.com/docs/connect/connection-pooling).
