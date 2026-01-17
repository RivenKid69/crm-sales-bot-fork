"""REST API for SEO Rewriter."""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from .rewriter import Rewriter, RewriteStyle
from .plagiarism import PlagiarismDetector, PlagiarismReport, SimilarityMetrics
from .llm import OllamaClient
from .config import settings


# Request/Response models
class RewriteRequest(BaseModel):
    """Request to rewrite text."""

    text: str = Field(..., min_length=10, description="Text to rewrite")
    style: RewriteStyle = Field(default=RewriteStyle.STANDARD, description="Rewriting style")
    keywords: Optional[list[str]] = Field(default=None, description="SEO keywords to include")
    target_uniqueness: float = Field(
        default=95.0,
        ge=50.0,
        le=100.0,
        description="Target uniqueness percentage",
    )
    max_attempts: int = Field(default=3, ge=1, le=10, description="Maximum rewrite attempts")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "text": "Президент провёл встречу с министрами. На встрече обсуждались вопросы экономики.",
                    "style": "news",
                    "keywords": ["экономика", "развитие"],
                    "target_uniqueness": 95.0,
                }
            ]
        }
    }


class RewriteResponse(BaseModel):
    """Response with rewritten text."""

    original_text: str
    rewritten_text: str
    uniqueness_score: float
    is_unique: bool
    attempts: int
    style: str
    metrics: SimilarityMetrics


class CheckRequest(BaseModel):
    """Request to check plagiarism."""

    original: str = Field(..., min_length=10, description="Original text")
    rewritten: str = Field(..., min_length=10, description="Rewritten text")
    threshold: float = Field(default=95.0, ge=50.0, le=100.0, description="Uniqueness threshold")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    ollama_available: bool
    model: str


# Global instances
rewriter: Rewriter | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global rewriter
    rewriter = Rewriter()
    yield
    rewriter = None


# Create FastAPI app
app = FastAPI(
    title="SEO Rewriter API",
    description="AI-powered text rewriting with plagiarism detection",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check():
    """Check API and LLM health."""
    assert rewriter is not None

    ollama_ok = await rewriter.check_health()
    return HealthResponse(
        status="healthy" if ollama_ok else "degraded",
        ollama_available=ollama_ok,
        model=settings.ollama_model,
    )


@app.post("/rewrite", response_model=RewriteResponse, tags=["rewriter"])
async def rewrite_text(request: RewriteRequest):
    """Rewrite text to make it unique.

    The text will be rewritten using the specified style and checked
    for uniqueness using plagiarism detection algorithms.
    """
    assert rewriter is not None

    # Check LLM availability
    if not await rewriter.check_health():
        raise HTTPException(
            status_code=503,
            detail=f"LLM not available. Ensure Ollama is running with model '{settings.ollama_model}'",
        )

    # Create rewriter with custom settings
    custom_rewriter = Rewriter(
        max_attempts=request.max_attempts,
        target_uniqueness=request.target_uniqueness,
    )

    result = await custom_rewriter.rewrite(
        text=request.text,
        style=request.style,
        keywords=request.keywords,
    )

    return RewriteResponse(
        original_text=result.original_text,
        rewritten_text=result.rewritten_text,
        uniqueness_score=result.plagiarism_report.uniqueness_score,
        is_unique=result.plagiarism_report.is_unique,
        attempts=result.attempts,
        style=result.style_used.value,
        metrics=result.plagiarism_report.metrics,
    )


@app.post("/check", response_model=PlagiarismReport, tags=["plagiarism"])
async def check_plagiarism(request: CheckRequest):
    """Check similarity between two texts.

    Analyzes texts using multiple algorithms:
    - N-gram overlap
    - Jaccard similarity
    - SimHash (Charikar, 2002)
    - Winnowing (Schleimer et al., 2003)
    """
    detector = PlagiarismDetector(uniqueness_threshold=request.threshold / 100)
    return detector.analyze(request.original, request.rewritten)


@app.get("/styles", tags=["rewriter"])
async def list_styles():
    """List available rewriting styles."""
    return {
        "styles": [
            {
                "name": style.value,
                "description": {
                    "standard": "Balanced rewrite with good uniqueness",
                    "creative": "Creative rewrite with significant changes",
                    "conservative": "Careful rewrite preserving structure",
                    "news": "Optimized for news articles",
                }[style.value],
            }
            for style in RewriteStyle
        ]
    }


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the API server."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
