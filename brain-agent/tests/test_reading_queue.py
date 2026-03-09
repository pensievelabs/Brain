"""
Unit tests for the Distributed Reading Queue feature.

Tests:
1. create_reading_stub() — filename generation, frontmatter, wiki-link
2. append_to_file() — content appended, index updated
3. scan_stale_readings() — stale vs. fresh detection
4. format_bankruptcy_message() — formatting
5. update_frontmatter_date() — date reset
"""

import os
import sys
import tempfile
import shutil
from datetime import date, timedelta
from unittest.mock import MagicMock

# Add project root to path
sys.path.insert(0, os.path.expanduser("~/Documents/Brain/brain-agent"))

from modules.task_scheduler import (
    scan_stale_readings,
    format_bankruptcy_message,
    update_frontmatter_date,
    _extract_frontmatter_date,
    _has_tag,
    _extract_title,
)


# --- Fixtures ---

def make_vault(tmp_path):
    """Create a mock vault with 3-Resources/ directory."""
    vault_dir = os.path.join(tmp_path, "vault")
    resources_dir = os.path.join(vault_dir, "3-Resources")
    os.makedirs(resources_dir, exist_ok=True)
    return vault_dir


def write_reading_file(vault_dir, filename, age_days, title="Test Book"):
    """Write a mock reading file with a #to-read tag and a date N days ago."""
    resources_dir = os.path.join(vault_dir, "3-Resources")
    filepath = os.path.join(resources_dir, filename)
    file_date = (date.today() - timedelta(days=age_days)).isoformat()
    content = (
        f"---\n"
        f"date: {file_date}\n"
        f"tags:\n"
        f'  - "#resource"\n'
        f'  - "#to-read"\n'
        f'  - "#book"\n'
        f"---\n\n"
        f"# {title}\n\n"
        f"## Source\nhttps://example.com\n"
    )
    with open(filepath, "w") as f:
        f.write(content)
    return filepath


# --- Tests for task_scheduler.py ---

def test_extract_frontmatter_date():
    """Extract date from YAML frontmatter."""
    content = "---\ndate: 2025-06-15\ntags:\n  - test\n---\n\n# Hello"
    result = _extract_frontmatter_date(content)
    assert result == date(2025, 6, 15), f"Expected 2025-06-15, got {result}"
    print("  ✅ test_extract_frontmatter_date PASSED")


def test_extract_frontmatter_date_missing():
    """Return None when no date field exists."""
    content = "---\ntags:\n  - test\n---\n\n# Hello"
    result = _extract_frontmatter_date(content)
    assert result is None, f"Expected None, got {result}"
    print("  ✅ test_extract_frontmatter_date_missing PASSED")


def test_has_tag():
    """Detect tags in frontmatter."""
    content = '---\ntags:\n  - "#resource"\n  - "#to-read"\n---\n'
    assert _has_tag(content, "#to-read") is True
    assert _has_tag(content, "#project") is False
    print("  ✅ test_has_tag PASSED")


def test_extract_title():
    """Extract first H1 heading."""
    content = "---\ndate: 2025-01-01\n---\n\n# My Book Title\n\n## Section"
    result = _extract_title(content)
    assert result == "My Book Title", f"Expected 'My Book Title', got '{result}'"
    print("  ✅ test_extract_title PASSED")


def test_scan_stale_readings_finds_old():
    """Detect files older than 90 days."""
    tmp = tempfile.mkdtemp()
    try:
        vault_dir = make_vault(tmp)
        write_reading_file(vault_dir, "old-book.md", age_days=120, title="Old Book")
        write_reading_file(vault_dir, "new-book.md", age_days=10, title="New Book")

        stale = scan_stale_readings(vault_dir, stale_days=90)
        assert len(stale) == 1, f"Expected 1 stale item, got {len(stale)}"
        assert stale[0]["title"] == "Old Book"
        assert stale[0]["age_days"] >= 120
        print("  ✅ test_scan_stale_readings_finds_old PASSED")
    finally:
        shutil.rmtree(tmp)


def test_scan_stale_readings_empty():
    """No stale items when all are recent."""
    tmp = tempfile.mkdtemp()
    try:
        vault_dir = make_vault(tmp)
        write_reading_file(vault_dir, "fresh.md", age_days=5, title="Fresh")

        stale = scan_stale_readings(vault_dir, stale_days=90)
        assert len(stale) == 0, f"Expected 0 stale items, got {len(stale)}"
        print("  ✅ test_scan_stale_readings_empty PASSED")
    finally:
        shutil.rmtree(tmp)


def test_format_bankruptcy_message_empty():
    """Empty list should return clean message."""
    msg = format_bankruptcy_message([])
    assert "No stale reading items" in msg
    print("  ✅ test_format_bankruptcy_message_empty PASSED")


def test_format_bankruptcy_message_with_items():
    """Non-empty list should format correctly."""
    items = [
        {"filepath": "3-Resources/old-book.md", "title": "Old Book", "age_days": 120},
        {"filepath": "3-Resources/ancient.md", "title": "Ancient", "age_days": 365},
    ]
    msg = format_bankruptcy_message(items)
    assert "2" in msg
    assert "/archive_reading" in msg
    assert "/keep" in msg
    assert "Old Book" in msg
    print("  ✅ test_format_bankruptcy_message_with_items PASSED")


def test_update_frontmatter_date():
    """Date field should be updated to today."""
    tmp = tempfile.mkdtemp()
    try:
        filepath = os.path.join(tmp, "test.md")
        with open(filepath, "w") as f:
            f.write("---\ndate: 2024-01-01\ntags:\n  - test\n---\n\n# Hello")

        result = update_frontmatter_date(filepath)
        assert "Updated date" in result

        with open(filepath) as f:
            updated = f.read()
        assert date.today().isoformat() in updated
        print("  ✅ test_update_frontmatter_date PASSED")
    finally:
        shutil.rmtree(tmp)


# --- Tests for vault_tools.py ---

def test_create_reading_stub():
    """create_reading_stub() should generate correct file and response."""
    from config import Config
    
    tmp = tempfile.mkdtemp()
    try:
        # Mock config and memory
        config = MagicMock(spec=Config)
        config.VAULT_DIR = tmp
        memory = MagicMock()

        # Create 3-Resources/ dir
        os.makedirs(os.path.join(tmp, "3-Resources"), exist_ok=True)

        from vault.vault_tools import VaultManager
        vm = VaultManager(config, memory)

        result = vm.create_reading_stub(
            title="Thinking Fast and Slow",
            source_url="https://example.com/book",
            content_type="book",
            tags=["psychology", "decision-making"],
        )

        assert "created" in result, f"Expected 'created' in result: {result}"
        assert "thinking-fast-and-slow" in result

        # Verify file exists
        filepath = os.path.join(tmp, "3-Resources", "thinking-fast-and-slow.md")
        assert os.path.exists(filepath), f"File not created at {filepath}"

        # Verify content
        with open(filepath) as f:
            content = f.read()
        assert "date:" in content
        assert "#to-read" in content
        assert "#book" in content
        assert "Thinking Fast and Slow" in content
        assert "https://example.com/book" in content

        # Verify index was updated
        memory.upsert.assert_called_once()

        print("  ✅ test_create_reading_stub PASSED")
    finally:
        shutil.rmtree(tmp)


def test_create_reading_stub_duplicate():
    """Should not overwrite existing file."""
    tmp = tempfile.mkdtemp()
    try:
        config = MagicMock()
        config.VAULT_DIR = tmp
        memory = MagicMock()
        os.makedirs(os.path.join(tmp, "3-Resources"), exist_ok=True)

        from vault.vault_tools import VaultManager
        vm = VaultManager(config, memory)

        # Create first
        vm.create_reading_stub("Test Book", "", "book", [])
        # Create duplicate
        result = vm.create_reading_stub("Test Book", "", "book", [])
        assert "already_exists" in result
        print("  ✅ test_create_reading_stub_duplicate PASSED")
    finally:
        shutil.rmtree(tmp)


def test_append_to_file():
    """append_to_file() should append content and update index."""
    tmp = tempfile.mkdtemp()
    try:
        config = MagicMock()
        config.VAULT_DIR = tmp
        memory = MagicMock()

        from vault.vault_tools import VaultManager
        vm = VaultManager(config, memory)

        # Create a file to append to
        filepath = os.path.join(tmp, "test-project.md")
        with open(filepath, "w") as f:
            f.write("# Project\n\n## Next Actions\n- [ ] Existing task\n")

        result = vm.append_to_file("test-project.md", "- [ ] Read: [[new-book]]")
        assert "Appended" in result

        with open(filepath) as f:
            content = f.read()
        assert "- [ ] Read: [[new-book]]" in content
        assert "- [ ] Existing task" in content  # Original content preserved

        print("  ✅ test_append_to_file PASSED")
    finally:
        shutil.rmtree(tmp)


# --- Run all tests ---

if __name__ == "__main__":
    print("\n🧪 Running Distributed Reading Queue tests...\n")

    tests = [
        test_extract_frontmatter_date,
        test_extract_frontmatter_date_missing,
        test_has_tag,
        test_extract_title,
        test_scan_stale_readings_finds_old,
        test_scan_stale_readings_empty,
        test_format_bankruptcy_message_empty,
        test_format_bankruptcy_message_with_items,
        test_update_frontmatter_date,
        test_create_reading_stub,
        test_create_reading_stub_duplicate,
        test_append_to_file,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ {test_fn.__name__} FAILED: {e}")
            failed += 1

    print(f"\n📊 Results: {passed} passed, {failed} failed out of {len(tests)}\n")
    sys.exit(failed)
