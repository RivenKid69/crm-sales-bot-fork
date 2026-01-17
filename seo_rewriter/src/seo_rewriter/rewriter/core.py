"""Core rewriter logic."""

from dataclasses import dataclass, field

from ..llm import OllamaClient
from ..plagiarism import PlagiarismDetector, PlagiarismReport
from ..config import settings
from .prompts import (
    RewriteStyle,
    get_system_prompt,
    get_user_prompt,
    get_retry_prompt,
)


@dataclass
class RewriteResult:
    """Result of rewriting operation."""

    original_text: str
    rewritten_text: str
    plagiarism_report: PlagiarismReport
    attempts: int
    success: bool
    style_used: RewriteStyle
    keywords: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"[{status}] Uniqueness: {self.plagiarism_report.uniqueness_score:.1f}% "
            f"(attempts: {self.attempts})"
        )


class Rewriter:
    """Text rewriter with plagiarism checking.

    Rewrites text using LLM and verifies uniqueness using plagiarism detection.
    Automatically retries if uniqueness threshold is not met.
    """

    def __init__(
        self,
        llm_client: OllamaClient | None = None,
        plagiarism_detector: PlagiarismDetector | None = None,
        max_attempts: int | None = None,
        target_uniqueness: float | None = None,
    ):
        """Initialize rewriter.

        Args:
            llm_client: Ollama client for LLM inference
            plagiarism_detector: Detector for checking uniqueness
            max_attempts: Maximum rewrite attempts
            target_uniqueness: Target uniqueness percentage (0-100)
        """
        self.llm = llm_client or OllamaClient()
        self.detector = plagiarism_detector or PlagiarismDetector()
        self.max_attempts = max_attempts or settings.max_rewrite_attempts
        self.target_uniqueness = target_uniqueness or settings.target_uniqueness

    async def rewrite(
        self,
        text: str,
        style: RewriteStyle = RewriteStyle.STANDARD,
        keywords: list[str] | None = None,
        temperature: float = 0.7,
    ) -> RewriteResult:
        """Rewrite text with uniqueness guarantee.

        Args:
            text: Original text to rewrite
            style: Rewriting style preset
            keywords: Optional SEO keywords to include
            temperature: LLM temperature (higher = more creative)

        Returns:
            RewriteResult with rewritten text and metrics
        """
        system_prompt = get_system_prompt(style)
        user_prompt = get_user_prompt(text, keywords)

        best_result: str | None = None
        best_report: PlagiarismReport | None = None
        attempts = 0

        for attempt in range(self.max_attempts):
            attempts = attempt + 1

            # Increase temperature on retries for more variation
            current_temp = min(temperature + (attempt * 0.1), 1.0)

            if attempt == 0:
                # First attempt: normal rewrite
                prompt = user_prompt
            else:
                # Retry: use more aggressive prompt
                assert best_report is not None
                prompt = get_retry_prompt(
                    original_text=text,
                    uniqueness=best_report.uniqueness_score,
                    threshold=self.target_uniqueness,
                )

            # Generate rewritten text
            rewritten = await self.llm.generate(
                prompt=prompt,
                system=system_prompt,
                temperature=current_temp,
            )

            # Clean up response (remove any thinking tags if present)
            rewritten = self._clean_response(rewritten)

            # Check plagiarism
            report = self.detector.analyze(text, rewritten)

            # Track best result
            if best_report is None or report.uniqueness_score > best_report.uniqueness_score:
                best_result = rewritten
                best_report = report

            # Check if we passed
            if report.uniqueness_score >= self.target_uniqueness:
                return RewriteResult(
                    original_text=text,
                    rewritten_text=rewritten,
                    plagiarism_report=report,
                    attempts=attempts,
                    success=True,
                    style_used=style,
                    keywords=keywords or [],
                )

        # Return best attempt even if failed
        assert best_result is not None and best_report is not None
        return RewriteResult(
            original_text=text,
            rewritten_text=best_result,
            plagiarism_report=best_report,
            attempts=attempts,
            success=False,
            style_used=style,
            keywords=keywords or [],
        )

    async def quick_rewrite(
        self,
        text: str,
        style: RewriteStyle = RewriteStyle.STANDARD,
    ) -> str:
        """Quick rewrite without retry logic.

        Args:
            text: Text to rewrite
            style: Rewriting style

        Returns:
            Rewritten text (may not pass uniqueness check)
        """
        system_prompt = get_system_prompt(style)
        user_prompt = get_user_prompt(text)

        result = await self.llm.generate(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.7,
        )

        return self._clean_response(result)

    def _clean_response(self, text: str) -> str:
        """Clean LLM response from artifacts."""
        # Remove common artifacts
        text = text.strip()

        # Remove thinking tags if model uses them
        import re
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)

        # Remove markdown code blocks if present
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)

        return text.strip()

    async def check_health(self) -> bool:
        """Check if LLM is available."""
        return await self.llm.check_health()
