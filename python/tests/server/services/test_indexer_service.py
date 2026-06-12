"""Tests for IndexerService — file writer and index maintainer."""

import os
import tempfile

import pytest

from src.server.services.knowledge.indexer_service import IndexerService


@pytest.fixture
def indexer():
    return IndexerService()


@pytest.fixture
def project_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# --- slugify_topic ---


class TestSlugifyTopic:
    def test_normal_text(self, indexer: IndexerService):
        assert indexer.slugify_topic("Getting Started with FastAPI") == "getting-started-with-fastapi"

    def test_already_slugified(self, indexer: IndexerService):
        assert indexer.slugify_topic("already-slugified") == "already-slugified"

    def test_special_characters(self, indexer: IndexerService):
        assert indexer.slugify_topic("C++ & Rust: A Comparison!") == "c-rust-a-comparison"

    def test_extra_whitespace(self, indexer: IndexerService):
        assert indexer.slugify_topic("  lots   of   spaces  ") == "lots-of-spaces"

    def test_consecutive_hyphens(self, indexer: IndexerService):
        assert indexer.slugify_topic("one---two---three") == "one-two-three"

    def test_leading_trailing_special(self, indexer: IndexerService):
        assert indexer.slugify_topic("---hello---") == "hello"

    def test_numbers(self, indexer: IndexerService):
        assert indexer.slugify_topic("Python 3.12 Features") == "python-312-features"

    def test_empty_string(self, indexer: IndexerService):
        assert indexer.slugify_topic("") == ""


# --- generate_unique_filename ---


class TestGenerateUniqueFilename:
    def test_basic_filename(self, indexer: IndexerService, project_dir: str):
        filename = indexer.generate_unique_filename(project_dir, "My Topic")
        assert filename == "my-topic.md"

    def test_collision_handling(self, indexer: IndexerService, project_dir: str):
        knowledge_dir = os.path.join(project_dir, ".cortex", "knowledge")
        os.makedirs(knowledge_dir, exist_ok=True)
        # Create a file to cause a collision
        with open(os.path.join(knowledge_dir, "my-topic.md"), "w") as f:
            f.write("existing")

        filename = indexer.generate_unique_filename(project_dir, "My Topic")
        assert filename == "my-topic-2.md"

    def test_multiple_collisions(self, indexer: IndexerService, project_dir: str):
        knowledge_dir = os.path.join(project_dir, ".cortex", "knowledge")
        os.makedirs(knowledge_dir, exist_ok=True)
        for name in ["my-topic.md", "my-topic-2.md", "my-topic-3.md"]:
            with open(os.path.join(knowledge_dir, name), "w") as f:
                f.write("existing")

        filename = indexer.generate_unique_filename(project_dir, "My Topic")
        assert filename == "my-topic-4.md"

    def test_no_collision_dir_missing(self, indexer: IndexerService, project_dir: str):
        # Knowledge dir doesn't exist yet — no collision possible
        filename = indexer.generate_unique_filename(project_dir, "Brand New")
        assert filename == "brand-new.md"


# --- write_materialized_file ---


class TestWriteMaterializedFile:
    @pytest.mark.asyncio
    async def test_creates_file(self, indexer: IndexerService, project_dir: str):
        content = "# Hello\nSome content."
        path = await indexer.write_materialized_file(project_dir, "hello.md", content)
        assert os.path.exists(path)
        with open(path) as f:
            assert f.read() == content

    @pytest.mark.asyncio
    async def test_creates_directories(self, indexer: IndexerService, project_dir: str):
        knowledge_dir = os.path.join(project_dir, ".cortex", "knowledge")
        assert not os.path.exists(knowledge_dir)

        await indexer.write_materialized_file(project_dir, "test.md", "content")
        assert os.path.isdir(knowledge_dir)

    @pytest.mark.asyncio
    async def test_overwrites_existing(self, indexer: IndexerService, project_dir: str):
        await indexer.write_materialized_file(project_dir, "test.md", "version 1")
        path = await indexer.write_materialized_file(project_dir, "test.md", "version 2")
        with open(path) as f:
            assert f.read() == "version 2"

    @pytest.mark.asyncio
    async def test_returns_full_path(self, indexer: IndexerService, project_dir: str):
        path = await indexer.write_materialized_file(project_dir, "out.md", "data")
        expected = os.path.join(project_dir, ".cortex", "knowledge", "out.md")
        assert path == expected


# --- remove_file ---


class TestRemoveFile:
    @pytest.mark.asyncio
    async def test_removes_existing_file(self, indexer: IndexerService, project_dir: str):
        path = await indexer.write_materialized_file(project_dir, "delete-me.md", "bye")
        assert os.path.exists(path)

        await indexer.remove_file(project_dir, "delete-me.md")
        assert not os.path.exists(path)

    @pytest.mark.asyncio
    async def test_noop_for_missing_file(self, indexer: IndexerService, project_dir: str):
        # Should not raise
        await indexer.remove_file(project_dir, "nonexistent.md")


# --- update_index ---


class TestUpdateIndex:
    @pytest.mark.asyncio
    async def test_empty_index(self, indexer: IndexerService, project_dir: str):
        await indexer.update_index(project_dir)
        index_path = os.path.join(project_dir, ".cortex", "index.md")
        assert os.path.exists(index_path)
        with open(index_path) as f:
            content = f.read()
        assert "No materialized knowledge files yet." in content
        assert "# .cortex Knowledge Index" in content

    @pytest.mark.asyncio
    async def test_index_with_frontmatter_entries(self, indexer: IndexerService, project_dir: str):
        file_content = (
            "---\n"
            "topic: FastAPI Basics\n"
            "materialized_at: 2026-03-06T10:30:00\n"
            "original_urls:\n"
            "  - https://fastapi.tiangolo.com/tutorial/\n"
            "---\n"
            "# FastAPI Basics\n"
            "Content here.\n"
        )
        await indexer.write_materialized_file(project_dir, "fastapi-basics.md", file_content)
        await indexer.update_index(project_dir)

        index_path = os.path.join(project_dir, ".cortex", "index.md")
        with open(index_path) as f:
            content = f.read()

        assert "## Materialized Knowledge" in content
        assert "[FastAPI Basics](knowledge/fastapi-basics.md)" in content
        assert "2026-03-06" in content
        assert "https://fastapi.tiangolo.com/tutorial/" in content

    @pytest.mark.asyncio
    async def test_index_strips_time_from_date(self, indexer: IndexerService, project_dir: str):
        file_content = (
            "---\n"
            "topic: Test Topic\n"
            "materialized_at: 2026-01-15T08:00:00Z\n"
            "---\n"
            "Content.\n"
        )
        await indexer.write_materialized_file(project_dir, "test-topic.md", file_content)
        await indexer.update_index(project_dir)

        index_path = os.path.join(project_dir, ".cortex", "index.md")
        with open(index_path) as f:
            content = f.read()
        # Should show date only, not full timestamp
        assert "2026-01-15" in content
        assert "T08:00:00" not in content

    @pytest.mark.asyncio
    async def test_index_fallback_topic_from_filename(self, indexer: IndexerService, project_dir: str):
        # No frontmatter at all
        await indexer.write_materialized_file(project_dir, "my-cool-topic.md", "# Just content")
        await indexer.update_index(project_dir)

        index_path = os.path.join(project_dir, ".cortex", "index.md")
        with open(index_path) as f:
            content = f.read()
        # Topic derived from filename: "my-cool-topic" -> "My Cool Topic"
        assert "[My Cool Topic]" in content
        assert "unknown" in content  # no materialized_at
        assert "local" in content  # no urls

    @pytest.mark.asyncio
    async def test_index_source_urls_fallback(self, indexer: IndexerService, project_dir: str):
        file_content = (
            "---\n"
            "topic: Alt Sources\n"
            "source_urls:\n"
            "  - https://example.com\n"
            "---\n"
            "Content.\n"
        )
        await indexer.write_materialized_file(project_dir, "alt-sources.md", file_content)
        await indexer.update_index(project_dir)

        index_path = os.path.join(project_dir, ".cortex", "index.md")
        with open(index_path) as f:
            content = f.read()
        assert "https://example.com" in content

    @pytest.mark.asyncio
    async def test_index_multiple_entries_sorted(self, indexer: IndexerService, project_dir: str):
        await indexer.write_materialized_file(project_dir, "beta.md", "---\ntopic: Beta\n---\n")
        await indexer.write_materialized_file(project_dir, "alpha.md", "---\ntopic: Alpha\n---\n")
        await indexer.write_materialized_file(project_dir, "gamma.md", "---\ntopic: Gamma\n---\n")
        await indexer.update_index(project_dir)

        index_path = os.path.join(project_dir, ".cortex", "index.md")
        with open(index_path) as f:
            content = f.read()

        alpha_pos = content.index("Alpha")
        beta_pos = content.index("Beta")
        gamma_pos = content.index("Gamma")
        assert alpha_pos < beta_pos < gamma_pos

    @pytest.mark.asyncio
    async def test_index_ignores_non_md_files(self, indexer: IndexerService, project_dir: str):
        knowledge_dir = os.path.join(project_dir, ".cortex", "knowledge")
        os.makedirs(knowledge_dir, exist_ok=True)
        with open(os.path.join(knowledge_dir, "notes.txt"), "w") as f:
            f.write("not markdown")
        await indexer.write_materialized_file(project_dir, "real.md", "---\ntopic: Real\n---\n")
        await indexer.update_index(project_dir)

        index_path = os.path.join(project_dir, ".cortex", "index.md")
        with open(index_path) as f:
            content = f.read()
        assert "notes.txt" not in content
        assert "[Real]" in content


# --- _extract_frontmatter ---


class TestExtractFrontmatter:
    def test_valid_frontmatter(self, indexer: IndexerService, project_dir: str):
        filepath = os.path.join(project_dir, "test.md")
        with open(filepath, "w") as f:
            f.write("---\ntopic: Hello\nkey: value\n---\nBody content")
        meta = indexer._extract_frontmatter(filepath)
        assert meta == {"topic": "Hello", "key": "value"}

    def test_no_frontmatter(self, indexer: IndexerService, project_dir: str):
        filepath = os.path.join(project_dir, "test.md")
        with open(filepath, "w") as f:
            f.write("# Just a heading\nNo frontmatter here.")
        meta = indexer._extract_frontmatter(filepath)
        assert meta == {}

    def test_invalid_yaml(self, indexer: IndexerService, project_dir: str):
        filepath = os.path.join(project_dir, "test.md")
        with open(filepath, "w") as f:
            f.write("---\n: invalid: yaml: [broken\n---\nBody")
        meta = indexer._extract_frontmatter(filepath)
        assert meta == {}

    def test_missing_file(self, indexer: IndexerService):
        meta = indexer._extract_frontmatter("/nonexistent/path/file.md")
        assert meta == {}
