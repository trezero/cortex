"""
MaterializationService — orchestrates knowledge materialization.

Coordinates RAG search, LLM synthesis, file writing, and DB tracking
to materialize Vector DB knowledge into local project repos.
"""

from datetime import UTC, datetime
from typing import Any

import yaml

from ...config.logfire_config import get_logger
from ...models.materialization import MaterializationRecord, MaterializationResult
from ...utils import get_supabase_client
from ...utils.progress.progress_tracker import ProgressTracker
from ..search.rag_service import RAGService
from .indexer_service import IndexerService

logger = get_logger(__name__)

TABLE = "cortex_materialization_history"


class MaterializationService:
    def __init__(self, supabase_client=None):
        self.supabase = supabase_client or get_supabase_client()
        self.indexer = IndexerService()

    async def check_existing(self, topic: str, project_id: str) -> MaterializationRecord | None:
        """Check if topic is already materialized (active or pending) for this project."""
        result = (
            self.supabase.table(TABLE)
            .select("*")
            .eq("project_id", project_id)
            .eq("topic", topic)
            .in_("status", ["active", "pending"])
            .execute()
        )
        if result.data:
            return MaterializationRecord(**result.data[0])
        return None

    async def list_materializations(self, project_id: str | None = None, status: str | None = None) -> list[MaterializationRecord]:
        """List materialization records, optionally filtered by project and/or status."""
        query = self.supabase.table(TABLE).select("*")
        if project_id:
            query = query.eq("project_id", project_id)
        if status:
            query = query.eq("status", status)
        query = query.order("materialized_at", desc=True)
        result = query.execute()
        return [MaterializationRecord(**row) for row in result.data]

    async def create_record(
        self,
        project_id: str,
        project_path: str,
        topic: str,
        filename: str,
        file_path: str,
        source_ids: list[str],
        original_urls: list[str],
        synthesis_model: str | None,
        word_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a new materialization history record. Returns the record ID."""
        result = (
            self.supabase.table(TABLE)
            .insert({
                "project_id": project_id,
                "project_path": project_path,
                "topic": topic,
                "filename": filename,
                "file_path": file_path,
                "source_ids": source_ids,
                "original_urls": original_urls,
                "synthesis_model": synthesis_model,
                "word_count": word_count,
                "metadata": metadata or {},
            })
            .execute()
        )
        return result.data[0]["id"]

    async def mark_accessed(self, materialization_id: str) -> None:
        """Increment the access count and update last_accessed_at via database RPC."""
        self.supabase.rpc("increment_access_count", {"record_id": materialization_id}).execute()

    async def update_status(self, materialization_id: str, status: str) -> None:
        """Update the status of a materialization record."""
        now = datetime.now(UTC).isoformat()
        (
            self.supabase.table(TABLE)
            .update({"status": status, "updated_at": now})
            .eq("id", materialization_id)
            .execute()
        )

    async def delete_record(self, materialization_id: str) -> None:
        """Delete a materialization record."""
        self.supabase.table(TABLE).delete().eq("id", materialization_id).execute()

    async def get_record(self, materialization_id: str) -> MaterializationRecord | None:
        """Get a single materialization record by ID."""
        result = self.supabase.table(TABLE).select("*").eq("id", materialization_id).execute()
        if result.data:
            return MaterializationRecord(**result.data[0])
        return None

    async def materialize(
        self,
        topic: str,
        project_id: str,
        project_path: str,
        progress_id: str | None = None,
        agent_context: str | None = None,
    ) -> MaterializationResult:
        """Full orchestration pipeline: search -> synthesize -> write -> track.

        Checks for an existing materialization first (returns it if found),
        then performs RAG search, LLM synthesis, file writing, and DB tracking.

        Args:
            topic: The knowledge topic to materialize.
            project_id: Cortex project ID.
            project_path: Filesystem path to the project repository.
            progress_id: Optional progress tracker ID for status updates.
            agent_context: Optional context from the requesting agent.

        Returns:
            MaterializationResult indicating success/failure and file details.
        """
        # Normalize topic to prevent case-sensitive duplicates
        topic = topic.strip().lower()

        # Step 1: Check for existing active or pending materialization
        existing = await self.check_existing(topic, project_id)
        if existing:
            await self.mark_accessed(existing.id)
            return MaterializationResult(
                success=True,
                file_path=existing.file_path,
                filename=existing.filename,
                word_count=existing.word_count,
                materialization_id=existing.id,
            )

        # Step 2: Create pending record as a concurrency claim
        pending_id = await self.create_record(project_id, project_path, topic, "", "", [], [], "", 0)
        await self.update_status(pending_id, "pending")

        # Step 3: Set up progress tracking
        tracker = ProgressTracker(progress_id, "materialization") if progress_id else None

        try:
            # Step 4: RAG search for relevant content
            if tracker:
                tracker.state.update({"status": "searching", "progress": 10})
            rag = RAGService(supabase_client=self.supabase)
            search_results = await rag.search_documents(query=topic, match_count=10, use_hybrid_search=True)
            if not search_results:
                await self.delete_record(pending_id)
                return MaterializationResult(success=False, reason="no_relevant_content")

            # Step 5: Filter chunks (minimum 50 chars) and build ChunkData
            MIN_CHUNK_LENGTH = 50
            from src.agents.synthesizer_agent import ChunkData, SourceInfo, SynthesizerAgent, SynthesizerDeps

            chunks = [
                ChunkData(
                    content=r["content"],
                    source_id=r.get("source_id", ""),
                    url=r.get("url"),
                    title=r.get("title"),
                )
                for r in search_results
                if len(r.get("content", "").strip()) >= MIN_CHUNK_LENGTH
            ]
            if not chunks:
                await self.delete_record(pending_id)
                return MaterializationResult(success=False, reason="no_relevant_content")

            # Build source map for deduplication
            source_map: dict[str, SourceInfo] = {}
            for r in search_results:
                sid = r.get("source_id", "")
                if sid and sid not in source_map:
                    source_map[sid] = SourceInfo(source_id=sid, title=r.get("title", ""), url=r.get("url"))

            # Step 6: Synthesize chunks into a cohesive document
            if tracker:
                tracker.state.update({"status": "synthesizing", "progress": 40})
            deps = SynthesizerDeps(topic=topic, chunks=chunks, source_metadata=list(source_map.values()))
            synthesizer = SynthesizerAgent()
            synthesized = await synthesizer.synthesize(deps)

            # Step 7: Build frontmatter and full file content
            if tracker:
                tracker.state.update({"status": "writing", "progress": 70})
            source_urls = synthesized.source_urls or [s.url for s in source_map.values() if s.url]
            source_ids = list(source_map.keys())
            frontmatter = {
                "cortex_source": "vector_archive",
                "materialized_at": datetime.now(UTC).isoformat(),
                "topic": topic,
                "source_urls": source_urls,
                "source_ids": source_ids,
                "synthesis_model": synthesizer.model,
                "materialization_id": pending_id,
            }
            full_content = f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n\n{synthesized.content}"

            # Step 8: Write file and update index
            filename = self.indexer.generate_unique_filename(project_path, topic)
            await self.indexer.write_materialized_file(project_path, filename, full_content)
            await self.indexer.update_index(project_path)

            # Step 9: Finalize DB record (pending -> active)
            file_path = f".cortex/knowledge/{filename}"
            now = datetime.now(UTC).isoformat()
            self.supabase.table(TABLE).update({
                "filename": filename,
                "file_path": file_path,
                "source_ids": source_ids,
                "original_urls": source_urls,
                "synthesis_model": synthesizer.model,
                "word_count": synthesized.word_count,
                "status": "active",
                "metadata": {"agent_context": agent_context} if agent_context else {},
                "updated_at": now,
            }).eq("id", pending_id).execute()

            if tracker:
                tracker.state.update({"status": "completed", "progress": 100, "file_path": file_path})

            return MaterializationResult(
                success=True,
                file_path=file_path,
                filename=filename,
                word_count=synthesized.word_count,
                summary=synthesized.summary,
                materialization_id=pending_id,
            )

        except Exception as e:
            logger.error(f"Materialization failed | topic={topic} | error={e}", exc_info=True)
            await self.delete_record(pending_id)
            if tracker:
                tracker.state.update({"status": "failed", "progress": 0, "error": str(e)})
            return MaterializationResult(success=False, reason=str(e))
