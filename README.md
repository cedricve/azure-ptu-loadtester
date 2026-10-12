# Azure PTU Load Tester

Send equal, concurrent request loads to two Azure OpenAI or Azure AI Foundry
chat-completions endpoints and compare their end-to-end response latency.

## Setup

Open the repository in its devcontainer. The container installs the project and
test dependencies automatically.

Copy `loadtest.example.toml` to `loadtest.toml` and set each full
chat-completions URL and deployment name. Keys are read from environment
variables and are never written to reports.

```sh
export AZURE_OPENAI_API_KEY_A="..."
export AZURE_OPENAI_API_KEY_B="..."
```

For Azure OpenAI, the URL normally has this shape:

```text
https://RESOURCE.openai.azure.com/openai/deployments/DEPLOYMENT/chat/completions
```

For the Azure OpenAI v1 API, both entries can use the same URL:

```text
https://RESOURCE.openai.azure.com/openai/v1/chat/completions
```

Set `model` to each Azure deployment name. Omit `api_version` for v1. For
models that require the newer token-limit field, set
`token_limit_parameter = "max_completion_tokens"`. Deployment-scoped URLs can
continue to set `api_version`; the tester preserves existing query parameters
and adds or replaces that query parameter.

## Run

```sh
azure-ptu-loadtest --rps 10 --duration 60
```

`--rps` is the offered load for **each** endpoint, so the example sends 10 RPS
to model A and 10 RPS to model B at the same time. Both endpoints receive the
same prompt and token limit. Use `--help` to see prompt, timeout, concurrency,
and output options.

Start with a low RPS and increase it gradually to avoid unexpected Azure usage
costs and rate-limit responses.

## Results

The terminal table compares successful-request mean, p50, p95, p99, and maximum
latency. Queue delay shows whether the client-side concurrency limit prevented
the requested load from being dispatched on schedule.

Each run also creates:

- A JSON report with configuration, summaries, failures, and individual samples.
- A CSV report with one row per request for further analysis.

Only successful requests contribute to latency percentiles. Failures and HTTP
status details are retained separately. API keys and prompt text are excluded
from report files.

## Test

```sh
pytest
```

## Example response

```sh
vscode ➜ /workspaces/azure-ptu-loadtester (main) $ azure-ptu-loadtest --rps 10 --duration 60
Running 10 RPS per endpoint (20 total) for 60s...

Endpoint  Success  Mean       p50       p95        p99         Max         Queue p95
--------  -------  ---------  --------  ---------  ----------  ----------  ---------
paygo     21/600   3055.5 ms  950.4 ms  1589.6 ms  36311.5 ms  44992.0 ms  6.1 ms
ptu       281/600  1201.1 ms  931.2 ms  1389.4 ms  2103.0 ms   36219.2 ms  5.7 ms

Reports: results/loadtest-20261012T120327Z.json and results/loadtest-20261012T120327Z.csv
vscode ➜ /workspaces/azure-ptu-loadtester (main) $
```
