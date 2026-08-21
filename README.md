# Azure DevOps PR Reviewer

A local command-line tool that uses GitHub Copilot to review an Azure DevOps pull request. It retrieves pull-request metadata and the complete file diff through read-only Azure DevOps REST API calls, then asks Copilot for concrete, evidence-based findings.

The code is split into reusable client, tool, and orchestration layers so the same capabilities can later be exposed through a local MCP server. Only Azure DevOps pull requests are supported today.

## Features

- Infers the Azure DevOps project and repository from a pull-request ID
- Reviews added, modified, deleted, and renamed text files
- Keeps the Azure DevOps integration read-only
- Restricts the Copilot session to the two registered Azure DevOps tools
- Streams the review to the terminal
- Provides typed tool inputs and outputs suitable for future MCP reuse

## Requirements

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/) (recommended), or another Python package manager
- GitHub Copilot access and a working GitHub Copilot CLI/SDK login
- An Azure DevOps personal access token (PAT) with **Code: Read** permission

## Setup

1. Install the project and its dependencies:

   ```bash
   uv sync
   ```

2. Copy the environment template:

   **PowerShell**

   ```powershell
   Copy-Item .env-template .env
   ```

   **macOS/Linux**

   ```bash
   cp .env-template .env
   ```

3. Set the values in `.env`:

   ```dotenv
   ADO_ORGANIZATION=your-organization
   ADO_PAT=your-read-only-personal-access-token
   ```

   `ADO_ORGANIZATION` is the organization segment from `https://dev.azure.com/<organization>`. The `.env` file is ignored by Git; never commit a real PAT.

## Usage

Run a review by pull-request ID:

```bash
uv run ado-pr-review 1234
```

Override the configured organization or review timeout when needed:

```bash
uv run ado-pr-review 1234 --organization my-organization --timeout 600
```

Show tool execution progress:

```bash
uv run ado-pr-review 1234 --verbose
```

For all options:

```bash
uv run ado-pr-review --help
```

The process exits with code `0` after a completed review, `1` for configuration/API/runtime failures, and `130` when interrupted.

## Development

Run the tests and quality checks:

```bash
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
```

Install the pre-commit hooks if desired:

```bash
uv run pre-commit install
```

## Project structure

```text
pr_reviewer/
  ado_client.py   # Read-only Azure DevOps REST client
  ado_tools.py    # Typed Copilot tool adapters
  reviewer.py     # Copilot review orchestration
  cli.py          # Argument parsing and terminal event rendering
tests/             # Unit tests for the client, tools, and CLI
samples/           # Incremental GitHub Copilot SDK examples
```

## Current limitations and roadmap

- Azure DevOps is the only source-control provider.
- Binary file content is not included in generated text diffs.
- The tool reports findings locally; it does not post comments or modify a pull request.
- MCP transport is not implemented yet. A future local MCP server can reuse `AdoClient` and the typed data models without coupling transport concerns to the CLI.

## Security

Use the minimum PAT scope (**Code: Read**) and rotate tokens regularly. The reviewer uses an isolated Copilot session whose available tool allowlist contains only its read-only pull-request metadata and diff tools. PAT values are sent only to Azure DevOps for API authentication and are not included in Copilot tool results.
