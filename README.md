# ALT-Repo

Ever felt that we give too much control over our open source projects to AI-centric corporations? If yes, this repo shows an alternative: a self-hosted Gitea setup paired with a local-first AI pull request review service.

`local-ai-pr-reviewer` receives Gitea pull request webhooks, fetches the PR diff, sends that diff to a local OpenAI-compatible LLM server such as LM Studio, generates a concise markdown review, and posts the review back to the pull request as a general comment.

## Why local-first AI review is useful

Running review generation against a local model keeps source diffs on your machine or LAN, reduces external dependency risk, and makes it practical to experiment with smaller or specialized models without wiring in a cloud provider.

## What it does

- Accepts Gitea pull request webhooks.
- Filters to relevant pull request actions: `opened`, `synchronized`, and `reopened`.
- Fetches the pull request diff from Gitea.
- Redacts likely secrets and trims oversized diffs before prompting the model.
- Calls a local OpenAI-compatible `/v1/chat/completions` API.
- Writes a markdown review in manual CLI mode.
- Posts the review back to the Gitea pull request as a general issue comment.

## What it does not do

- No frontend UI.
- No cloud LLM providers.
- No line-level review comments in the MVP.
- No database, queue, retry worker, or background job system yet.

## Project structure

```text
local-ai-pr-reviewer/
├── app/
├── prompts/
├── samples/
├── output/
├── tests/
├── config.yaml
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Recommended setup: Docker first

This is the recommended way to run the project. It starts:

- PostgreSQL for Gitea
- Gitea itself
- the `local-ai-pr-reviewer` API service

LM Studio is still expected to run on your host machine, with its OpenAI-compatible server enabled.

### 1. Start LM Studio

- Run LM Studio locally.
- Load your chosen model, for example `gemma-3-4b-it`.
- Enable the OpenAI-compatible server.
- By default this project expects LM Studio at `http://localhost:1234/v1`.

### 2. Export required secrets

```bash
export GITEA_TOKEN="your-gitea-token"
export GITEA_WEBHOOK_SECRET="your-webhook-secret"
```

`GITEA_TOKEN` must belong to a user that can read pull requests and create PR comments in Gitea.

### 3. Start the stack

```bash
docker compose up --build
```

This gives you:

- Gitea at `http://localhost:3000`
- the reviewer API at `http://localhost:8080`

Inside Docker, the reviewer service uses:

- `http://gitea:3000` for Gitea
- `http://host.docker.internal:1234/v1` for LM Studio on the host

### 4. Create the webhook in Gitea

Configure a repository webhook that points to:

```text
http://localhost:8080/webhooks/gitea
```

Use the same secret value as `GITEA_WEBHOOK_SECRET` so the app can verify the `X-Gitea-Signature` header.

The included `docker-compose.yml` already adds `local-ai-pr-reviewer` to Gitea's webhook allow-list.

### 5. Verify the service

Health check:

```bash
curl http://localhost:8080/health
```

Expected response:

```json
{"status":"ok"}
```

### 6. Useful Docker commands

Start in the background:

```bash
docker compose up -d --build
```

View logs:

```bash
docker compose logs -f local-ai-pr-reviewer
```

Stop everything:

```bash
docker compose down
```

## Local Python setup

If you prefer to run the reviewer service directly on your machine instead of in Docker, use this path.

### 1. Install dependencies

Use Python 3.12 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Export required secrets

```bash
export GITEA_TOKEN="your-gitea-token"
export GITEA_WEBHOOK_SECRET="your-webhook-secret"
```

### 3. Review config

By default, `config.yaml` assumes:

- Gitea at `http://localhost:3000`
- LM Studio at `http://localhost:1234/v1`

You can keep those defaults or override them with environment variables.

### 4. Run the API locally

```bash
uvicorn app.main:app --reload --port 8080
```

### 5. Verify locally

```bash
curl http://localhost:8080/health
```

## Manual CLI test

The CLI mode is useful for prompt and model testing without sending a webhook.

Run:

```bash
python -m app.main --diff samples/example.diff
```

This loads the configured prompt, sends the sample diff to the local LLM, and writes the resulting markdown report to `output/review.md`.

## LM Studio assumptions

- LM Studio is running locally.
- Its OpenAI-compatible server is enabled.
- For host-based runs, the default endpoint is `http://localhost:1234/v1`.
- For Docker Compose runs, the app uses `http://host.docker.internal:1234/v1`.
- The configured model name matches the model loaded in LM Studio, for example `gemma-3-4b-it`.

## Gitea token setup

Create a Gitea API token with permission to read pull requests and create comments. The app reads the token from the environment variable named in `gitea.api_token_env`, which defaults to `GITEA_TOKEN`.

## Configuration notes

`config.yaml` remains the default source of truth, but these environment variables can override the most common runtime values:

- `LOCAL_AI_PR_REVIEWER_GITEA_BASE_URL`
- `LOCAL_AI_PR_REVIEWER_LLM_BASE_URL`
- `LOCAL_AI_PR_REVIEWER_LLM_MODEL`
- `LOCAL_AI_PR_REVIEWER_LLM_TEMPERATURE`
- `LOCAL_AI_PR_REVIEWER_LLM_TIMEOUT_SECONDS`
- `LOCAL_AI_PR_REVIEWER_REVIEW_MAX_DIFF_CHARS`
- `LOCAL_AI_PR_REVIEWER_SAFETY_LOCAL_ONLY`

Examples:

```bash
export LOCAL_AI_PR_REVIEWER_LLM_BASE_URL="http://host.docker.internal:1234/v1"
export LOCAL_AI_PR_REVIEWER_LLM_MODEL="gemma-3-4b-it"
```

## Testing

Run:

```bash
pytest
```

## Limitations

- This is not a replacement for human review.
- The MVP posts general PR comments only.
- There is no persistent storage yet.
- There is no queue or retry system yet.

## Roadmap

- Add line-level comments if Gitea supports them cleanly for the target workflow.
- Introduce a clearer provider abstraction for other local OpenAI-compatible servers.
- Move to structured JSON review output.
- Replace or update previous bot comments instead of always posting a new one.
- Add async job processing for larger repositories.
- Support multi-model review strategies.
- Add GitHub and GitLab support.
