"""
Synthesizer Agent — transforms raw RAG chunks into cohesive Markdown documents.
"""

import logging
import os
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from .base_agent import CortexDependencies, BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class ChunkData:
    """A single RAG chunk with its source metadata."""

    content: str
    source_id: str
    url: str | None = None
    title: str | None = None
    chunk_number: int | None = None


@dataclass
class SourceInfo:
    """Metadata about a knowledge-base source."""

    source_id: str
    title: str
    url: str | None = None


@dataclass
class SynthesizerDeps(CortexDependencies):
    """Dependencies for the synthesizer agent."""

    topic: str = ""
    chunks: list[ChunkData] = field(default_factory=list)
    source_metadata: list[SourceInfo] = field(default_factory=list)


class SynthesizedDocument(BaseModel):
    """Structured output produced by the synthesizer agent."""

    title: str = Field(description="Human-readable title for the document")
    content: str = Field(description="Full Markdown content (without frontmatter)")
    summary: str = Field(description="One-sentence summary of the document")
    source_urls: list[str] = Field(description="URLs of sources used")
    word_count: int = Field(description="Word count of the content")


SYSTEM_PROMPT = """\
You are a technical documentation synthesizer. Your job is to take
fragmented text chunks from a knowledge base and produce a single, cohesive Markdown document.

Rules:
- Produce clean Markdown with logical headers (##, ###)
- Deduplicate overlapping content from different chunks
- Organize information logically, not in chunk order
- Include code blocks with language tags where relevant
- Be concise — synthesize, don't pad
- End with a ## Sources section listing all source URLs
- Do NOT include YAML frontmatter — that will be added separately
- Write the title as an H1 at the top of the document
"""


class SynthesizerAgent(BaseAgent[SynthesizerDeps, SynthesizedDocument]):
    """Transforms raw RAG chunks into cohesive Markdown documents."""

    def __init__(self, model: str | None = None, **kwargs):
        if model is None:
            model = os.getenv("SYNTHESIZER_MODEL", "openai:gpt-4.1-nano")
        super().__init__(
            model=model,
            name="SynthesizerAgent",
            retries=3,
            enable_rate_limiting=True,
            **kwargs,
        )

    def _create_agent(self, **kwargs) -> Agent:
        agent = Agent(
            model=self.model,
            deps_type=SynthesizerDeps,
            result_type=SynthesizedDocument,
            system_prompt=SYSTEM_PROMPT,
            **kwargs,
        )

        @agent.system_prompt
        async def add_chunk_context(ctx: RunContext[SynthesizerDeps]) -> str:
            chunks_text = "\n\n---\n\n".join(
                f"[Source: {c.url or c.source_id}]\n{c.content}" for c in ctx.deps.chunks
            )
            return f"Topic to synthesize: {ctx.deps.topic}\n\nSource chunks:\n{chunks_text}"

        return agent

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def synthesize(self, deps: SynthesizerDeps) -> SynthesizedDocument:
        """Synthesize chunks into a cohesive document.

        Args:
            deps: Dependencies containing the topic, chunks, and source metadata.

        Returns:
            A SynthesizedDocument with the merged Markdown content.
        """
        prompt = f"Synthesize the following chunks about '{deps.topic}' into a cohesive document."
        return await self.run(prompt, deps=deps)
