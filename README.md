# local-ai-pr-reviewer

`local-ai-pr-reviewer` is a local-first AI pull request review harness for Gitea. It receives pull request webhooks, fetches the PR diff from Gitea, sends the diff to a local OpenAI-compatible LLM server such as LM Studio, generates a concise markdown review, and posts that review back to the pull request as a general comment.

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
├── requirements.txt
└── README.md
```

## Setup instructions

1. Use Python 3.12 or newer.
2. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Review `config.yaml` and adjust local URLs or model name if needed.
4. Export the required environment variables:

```bash
export GITEA_TOKEN="your-gitea-token"
export GITEA_WEBHOOK_SECRET="your-webhook-secret"
```

## Docker setup

The project includes a `Dockerfile` and a Compose service for the Python app. In the default Compose setup:

- Gitea stays reachable inside Docker as `http://gitea:3000`
- LM Studio is expected on the host as `http://host.docker.internal:1234/v1`
- the review service is exposed on `http://localhost:8080`

Start the full stack with:

```bash
docker compose up --build
```

If your local LLM server is not on `http://localhost:1234/v1`, override it with:

```bash
export LOCAL_AI_PR_REVIEWER_LLM_BASE_URL="http://host.docker.internal:1234/v1"
docker compose up --build
```

The Compose file already sets Docker-friendly defaults for the Gitea and LLM base URLs, so you usually do not need to edit `config.yaml` just to run in containers.

## LM Studio setup assumptions

- LM Studio is running locally.
- Its OpenAI-compatible server is enabled.
- For host-based runs, the configured endpoint is `http://localhost:1234/v1`.
- For Docker Compose runs, the app uses `http://host.docker.internal:1234/v1`.
- The configured model name matches the model loaded in LM Studio, for example `gemma-3-4b-it`.

## Gitea token setup

Create a Gitea API token with permission to read pull requests and create comments. The app reads the token from the environment variable named in `gitea.api_token_env`, which defaults to `GITEA_TOKEN`.

## Webhook setup

Configure a Gitea repository webhook that points to:

```text
http://localhost:8080/webhooks/gitea
```

Use the same secret value as `GITEA_WEBHOOK_SECRET` so the app can verify the `X-Gitea-Signature` header when the secret is configured.

If you are creating the webhook from the Gitea containerized setup in this repo, `docker-compose.yml` already allows the `local-ai-pr-reviewer` host in Gitea's webhook allow-list.

## Manual CLI test

Run:

```bash
python -m app.main --diff samples/example.diff
```

This loads the configured prompt, sends the sample diff to the local LLM, and writes the resulting markdown report to `output/review.md`.

## API and webhook run command

Run:

```bash
uvicorn app.main:app --reload --port 8080
```

Health check:

```bash
curl http://localhost:8080/health
```

## Testing

Run:

```bash
pytest
```

## Configuration notes

`config.yaml` remains the default source of truth, but these environment variables can override the most common runtime values:

- `LOCAL_AI_PR_REVIEWER_GITEA_BASE_URL`
- `LOCAL_AI_PR_REVIEWER_LLM_BASE_URL`
- `LOCAL_AI_PR_REVIEWER_LLM_MODEL`
- `LOCAL_AI_PR_REVIEWER_LLM_TEMPERATURE`
- `LOCAL_AI_PR_REVIEWER_LLM_TIMEOUT_SECONDS`
- `LOCAL_AI_PR_REVIEWER_REVIEW_MAX_DIFF_CHARS`
- `LOCAL_AI_PR_REVIEWER_SAFETY_LOCAL_ONLY`

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
