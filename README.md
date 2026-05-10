# Local AI Coding Agent

A v0 local AI coding agent that can inspect a local Git repository, formulate a plan, seek human approval, and execute tool actions within a secure Docker sandbox to produce a reviewable code diff.

## Features

- **Local-First / Sandbox**: Operates inside an isolated Docker container (`python:3.10-slim`).
- **Human Approval**: Pauses for approval before making any plan modifications or running high-risk commands (e.g. `npm install`, `write_file`).
- **Tool Access**: Comes with `read_file`, `write_file`, `list_files`, `apply_patch`, `run_shell`, `git_diff`, and `git_status`.
- **Audit Logging**: Keeps structured JSONL tool call logs and patches inside `.runs/<timestamp>/`.
- **LLM Agnostic**: Connects to OpenAI or any OpenAI-compatible local model (like Ollama).

## Architecture

```text
    +-------------------+       +-----------------------+       +-------------------+
    |    CLI (User)     | <---> |   Core Agent Loop     | <---> |  LLM Provider     |
    +-------------------+       +-----------------------+       +-------------------+
             ^                              |                             |
             | Approval               Tool Calls & Results                |
             v                              |                             v
    +-------------------+       +-----------------------+       +-------------------+
    |    Audit Log      | <---- |     Tool Registry     |       | Local / Cloud API |
    | (.runs/ directory)|       +-----------------------+       +-------------------+
    +-------------------+                   |
                                            v
                                +-----------------------+
                                |    Docker Sandbox     |
                                |  (Isolated Workspace) |
                                +-----------------------+
```

## Installation

1. Make sure you have Docker running locally.
2. Install the package:
```bash
pip install -e .
```

## Usage

### 1. Set up your model

Export your API key (if using OpenAI):
```bash
export OPENAI_API_KEY="your-api-key"
```
Or, if using a local Ollama model running the OpenAI compatibility layer, use the `--base-url` flag in the CLI.

### 2. Run the agent

Point the agent at a local repository path with a natural language task:

```bash
agent run --repo ./demo-app --task "Add a unit test for the add_user function in app.py"
```

### Example Demo Output

```text
Initializing agent...
Preparing sandbox for './demo-app'...
Starting task: Add a unit test for the add_user function in app.py

--- Step 1 ---
Agent:
I will list the files in the directory to see what is available, then read `app.py`.

Tool Call: list_files(.)
Tool Result (truncated): app.py...

--- Step 2 ---
Tool Call: read_file({"file_path": "app.py"})
Tool Result (truncated): def add_user(name): pass...

--- Step 3 ---
Agent:
I'll create a plan to write a test file `test_app.py`.

Plan:
1. Create `test_app.py` importing `add_user`.
2. Add a simple assert.
3. Run pytest.

[APPROVAL REQUIRED] The agent has proposed a plan. Do you approve?
Approve? [y/N]: y

--- Step 4 ---
Tool Call: write_file({"file_path": "test_app.py", "content": "..."})
Tool Result (truncated): Successfully wrote to test_app.py...

--- Run Complete ---

Final Summary:
I successfully created `test_app.py` to test the `add_user` function.

Audit logs and diff saved to: .runs/2026-05-10T120000
```

Check `.runs/` to view the generated `.patch` diff file and apply it if satisfied!
