# SEO Rewriter

AI-powered text rewriting with plagiarism detection.

## Features

- Text rewriting using local LLM (Qwen3 via Ollama)
- Plagiarism detection based on scientific algorithms:
  - N-gram overlap analysis
  - Jaccard similarity
  - SimHash (Charikar, 2002)
  - Winnowing (Schleimer et al., 2003)
- Multiple rewriting styles (standard, creative, conservative, news)
- Automatic retry if uniqueness threshold not met
- CLI and REST API interfaces

## Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install
pip install -e .
```

## Prerequisites

Install and run Ollama with Qwen3:
```bash
ollama pull qwen3:8b
ollama serve
```

## Usage

### CLI

```bash
# Rewrite text
seo-rewriter rewrite "Your text here"

# Rewrite from file
seo-rewriter rewrite --file article.txt --output result.txt

# Use specific style
seo-rewriter rewrite "text" --style news

# Add SEO keywords
seo-rewriter rewrite "text" --keywords "seo,marketing"

# Check plagiarism between two texts
seo-rewriter check "original text" "rewritten text"

# List available models
seo-rewriter models

# Show configuration
seo-rewriter config
```

### REST API

```bash
# Start API server
seo-rewriter serve --port 8000

# API endpoints:
# POST /rewrite - Rewrite text
# POST /check - Check plagiarism
# GET /health - Health check
# GET /styles - List styles
# GET /docs - OpenAPI documentation
```

## Configuration

Environment variables (prefix `SEO_`):

| Variable | Default | Description |
|----------|---------|-------------|
| SEO_OLLAMA_BASE_URL | http://localhost:11434 | Ollama API URL |
| SEO_OLLAMA_MODEL | qwen3:8b | Model name |
| SEO_TARGET_UNIQUENESS | 95.0 | Target uniqueness % |
| SEO_MAX_REWRITE_ATTEMPTS | 3 | Max retry attempts |
