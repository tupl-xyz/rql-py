# RQL (Reasoning Query Language)

A minimal CLI application for AI-powered reasoning and data retrieval using Google GenAI.

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd rql-py

# Install dependencies
pip install -e .

# For development
pip install -e ".[dev]"
```

### Configuration

Create environment variables for API access:

```bash
export GEMINI_API_KEY="your-gemini-api-key"
export N8N_TOKEN="your-n8n-token"  # Optional, for executions API
```

Optionally initialize configuration:

```bash
rql init  # Creates ~/.rql/config.toml with defaults
```

### Getting Started with the REPL

The easiest way to start using RQL is through the interactive REPL:

```bash
# Launch the interactive REPL
rql

# OR explicitly
rql --help  # Shows available commands
```

The REPL provides:
- **Syntax highlighting** for RQL statements
- **Auto-completion** for keywords and commands
- **Multi-line input** support with smart submission
- **History** with search (Ctrl+R)
- **Contract management** for reproducible results
- **Built-in help system** (`:help`)

#### First Steps in the REPL

1. **Start the REPL**: Run `rql`
2. **Get help**: Type `:help` to see all available commands and syntax
3. **Configure a model**: `SET model = "gemini-2.5-flash";`
4. **Run your first query**: `SELECT * FROM TASK ANSWER(question: "What is RQL?");`

### Command Line Usage

```bash
# Execute a single RQL statement
rql exec "SET model = 'gemini-2.5-flash';"

# Run an RQL file
rql run examples/quickstart.rql

# Describe registered sources and policies
rql describe SOURCES
rql describe POLICIES

# Initialize configuration
rql init

# Show version
rql version
```

## CLI Commands Reference

### Core Commands

| Command | Arguments | Description |
|---------|-----------|-------------|
| `rql` | None | Launch interactive REPL (default command) |
| `rql exec` | `<statement>` | Execute a single RQL statement |
| `rql run` | `<file_path>` | Execute RQL statements from a file |
| `rql describe` | `SOURCES\|POLICIES` | Show registered sources or policies |
| `rql init` | None | Initialize configuration at `~/.rql/config.toml` |
| `rql version` | None | Show version information |

### Command Options

All commands support these options:

| Option | Description |
|--------|-------------|
| `--verbose`, `-v` | Enable verbose output with detailed logging |
| `--help`, `-h` | Show help for the command |

### Examples

```bash
# Basic usage
rql exec "SET model = 'gemini-2.5-flash';" --verbose
rql run my_script.rql -v
rql describe SOURCES

# File execution with error handling
rql run examples/demo.rql || echo "Script failed"
```

## REPL Commands Reference

The interactive REPL supports meta-commands prefixed with `:`:

### File Operations

| Command | Arguments | Description |
|---------|-----------|-------------|
| `:open` | `<file_path>` | Load file contents into the buffer for editing |
| `:save` | `[file_path]` | Save buffer to file (uses last opened if no path) |
| `:run` | `<file_path>` | Execute a file within the current session |

### Session Management

| Command | Arguments | Description |
|---------|-----------|-------------|
| `:reset` | None | Reset REPL session state (clears variables) |
| `:verbose` | `[on\|off]` | Toggle or set verbose mode |
| `:quit` | None | Exit the REPL |

### Information Commands

| Command | Arguments | Description |
|---------|-----------|-------------|
| `:help` | None | Show comprehensive help with syntax examples |
| `:describe` | `[SOURCES\|POLICIES]` | Describe registry state (defaults to SOURCES) |

### Contract Management

| Command | Arguments | Description |
|---------|-----------|-------------|
| `:contracts` | `[list\|last\|open <n>]` | Inspect reasoning contracts |
| `:replay` | `<contract.json>` | Replay a saved contract for reproducibility |

### Buffer Operations

| Command | Arguments | Description |
|---------|-----------|-------------|
| `:format` | None | Format the current buffer with basic indentation |

### REPL Keybindings

| Key Combination | Action |
|-----------------|--------|
| `Enter` | Submit statement (when complete and balanced) |
| `Shift+Enter` | Insert newline (continue multi-line input) |
| `Ctrl+R` | Force submit current buffer |
| `Ctrl+S` | Save buffer to file |
| `Alt+C` | Toggle contract pane visibility |
| `Ctrl+C` | Cancel current input |
| `Ctrl+D` | Exit REPL |

## RQL Language Reference

### Task-Based Queries

RQL v0.2.0 focuses on task-based deterministic execution:

#### Available Tasks

| Task | Arguments | Description |
|------|-----------|-------------|
| `ANSWER` | `question: <text>`, `context: REF(...)` | Answer questions with optional context and citations |
| `SUMMARIZE` | `text: <text>`, `focus: <aspect>`, `length: <constraint>`, `text_ref: REF(...)` | Summarize content with controls |
| `EXTRACT` | `schema: <json_schema>`, `input_text: <text>`, `input_ref: REF(...)` | Extract structured data matching schema |

#### Task Syntax

```sql
SELECT <items> FROM TASK <name>(<args>)
[WITH <params>]
[POLICY <policy>]
[REQUIRE DETERMINISM <level>]
[RETURN <format>]
[INTO <variable>];
```

#### SELECT Items

| Item | Description |
|------|-------------|
| `OUTPUT` | Primary task result |
| `EVIDENCE` | Supporting evidence/sources |
| `CONFIDENCE` | Confidence score |
| `*` | All available items |

#### Determinism Levels

| Level | Description |
|-------|-------------|
| `provider` | Default level with pinned models and non-stochastic decoding |
| `strong` | Strict JSON output with schema validation and two-pass execution |

### Basic Statements

#### SET - Configure session settings

| Setting | Type | Description |
|---------|------|-------------|
| `model` | string | Model identifier (e.g., "gemini-2.5-flash") |
| `temperature` | number | Sampling temperature (0.0 to 1.0) |
| `max_tokens` | number | Maximum tokens in response |
| `verbose` | boolean | Enable detailed logging |

```sql
SET model = "gemini-2.5-flash";
SET temperature = 0.1;
SET max_tokens = 512;
SET verbose = true;
```

#### DEFINE SOURCE - Register data sources
```sql
-- Google GenAI LLM source
DEFINE SOURCE gemini_flash TYPE LLM USING {
  "provider": "google-genai",
  "model": "gemini-2.5-flash"
} AS "Primary Gemini model";

-- n8n workflow source
DEFINE SOURCE retriever TYPE WORKFLOW USING {
  "kind": "n8n",
  "webhook": "https://n8n.example.com/webhook/retrieve"
};
```

#### DEFINE POLICY - Set governance rules
```sql
DEFINE POLICY require_citations AS {
  "input": {"forbid_pii": true},
  "output": {"require_citations": true, "hallucination_mode": "block_or_ask"},
  "logging": {"level": "full"}
};
```

#### DESCRIBE - Inspect registry

```sql
DESCRIBE SOURCES;   -- Show all registered data sources
DESCRIBE POLICIES;  -- Show all registered governance policies
```

### Task Examples

#### Simple Question Answering
```sql
SELECT * FROM TASK ANSWER(question: "What is RQL?");
```

#### Structured Data Extraction
```sql
SELECT OUTPUT FROM TASK EXTRACT(
  schema: {"name": {"type": "string"}, "age": {"type": "number"}},
  input_text: "John Doe is 30 years old"
) RETURN JSON;
```

#### Content Summarization with References
```sql
SELECT * FROM TASK SUMMARIZE(
  text_ref: REF(docs, {"path": "/readme.md"}),
  focus: "key features",
  length: "one paragraph"
) WITH decode.temperature = 0.1;
```

#### Deterministic Processing
```sql
SELECT OUTPUT FROM TASK ANSWER(
  question: "Analyze this data",
  context: REF(database, {"query": "SELECT * FROM users"})
)
REQUIRE DETERMINISM strong
RETURN JSON;
```

### Working with Variables

```sql
-- Store results in variables
SELECT * FROM TASK EXTRACT(
  schema: {"topics": {"type": "array"}},
  input_text: "Machine learning and AI are growing fields"
) INTO topics;

-- Use variables in subsequent queries
SELECT * FROM TASK ANSWER(
  question: "Explain these topics in detail",
  context: {topics}
);
```

### Policy Examples

```sql
-- Define a strict governance policy
DEFINE POLICY strict_mode AS {
  "input": {"forbid_pii": true},
  "output": {"require_citations": true, "hallucination_mode": "block"},
  "logging": {"level": "full"}
};

-- Use the policy in queries
SELECT * FROM TASK ANSWER(question: "What is GDPR?")
POLICY strict_mode
RETURN JSON;
```

## Architecture

- **Parser**: Lark-based grammar for RQL syntax
- **Engine**: Execution engine with pluggable executors
- **Policies**: Pre/post-execution governance and safety
- **Tracing**: Complete execution logging to JSONL
- **Runtime**: Session management and configuration

## Development

```bash
# Run tests
pytest

# Format code
black rql/ tests/
isort rql/ tests/

# Type checking
mypy rql/
```

## Configuration Files

### Global Config (`~/.rql/config.toml`)
```toml
[default]
model = "google-genai:gemini-2.5-flash"
temperature = 0.1
max_tokens = 512
trace_dir = "~/.rql/runs"
```

### Project Config (`rql.toml` in working directory)
```toml
[default]
model = "google-genai:gemini-2.5-pro"
trace_dir = "./traces"
```

## License

MIT License
