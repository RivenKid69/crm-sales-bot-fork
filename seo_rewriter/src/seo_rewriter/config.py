"""Configuration settings for SEO Rewriter."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Ollama settings
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:1.7b"  # Default Qwen3 model
    ollama_timeout: int = 120  # seconds

    # Rewriter settings
    max_rewrite_attempts: int = 3  # Retry if plagiarism check fails
    target_uniqueness: float = 95.0  # Minimum uniqueness percentage

    # Plagiarism detection thresholds
    ngram_size: int = 3  # For n-gram analysis
    shingle_size: int = 5  # For winnowing algorithm
    min_uniqueness_threshold: float = 0.95  # 95% unique

    class Config:
        env_prefix = "SEO_"
        env_file = ".env"


settings = Settings()
