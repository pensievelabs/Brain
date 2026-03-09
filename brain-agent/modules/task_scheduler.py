"""
Task Scheduler — Reading Queue Bankruptcy Protocol

Standalone module for detecting stale #to-read items in 3-Resources/.
Can be triggered via /prune command or scheduled as a cron job.
"""

import os
import re
import glob
import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)


def _extract_frontmatter_date(content: str) -> date | None:
    """Extract the date: field from YAML frontmatter."""
    fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).split('\n'):
            line = line.strip()
            if line.startswith('date:'):
                date_str = line.split(':', 1)[1].strip().strip('"').strip("'")
                try:
                    return date.fromisoformat(date_str)
                except ValueError:
                    pass
    return None


def _has_tag(content: str, tag: str) -> bool:
    """Check if a file's YAML frontmatter contains a specific tag."""
    fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if fm_match:
        return tag in fm_match.group(1)
    return False


def _extract_title(content: str) -> str:
    """Extract the first # heading as the title, or fall back to filename."""
    for line in content.split('\n'):
        if line.startswith('# ') and not line.startswith('##'):
            return line[2:].strip()
    return ""


def scan_stale_readings(vault_dir: str, stale_days: int = 90) -> list[dict]:
    """
    Scan 3-Resources/ for #to-read files older than stale_days.

    Returns a list of dicts with filepath, title, and age_days.
    """
    resources_dir = os.path.join(vault_dir, "3-Resources")
    if not os.path.isdir(resources_dir):
        logger.warning(f"Resources directory not found: {resources_dir}")
        return []

    today = date.today()
    stale_items = []

    files = glob.glob(os.path.join(resources_dir, "**", "*.md"), recursive=True)

    for filepath in files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            if not _has_tag(content, "#to-read"):
                continue

            # Get date from frontmatter, fall back to file mtime
            file_date = _extract_frontmatter_date(content)
            if file_date is None:
                mtime = os.path.getmtime(filepath)
                file_date = datetime.fromtimestamp(mtime).date()

            age_days = (today - file_date).days

            if age_days >= stale_days:
                title = _extract_title(content) or os.path.basename(filepath)
                rel_path = os.path.relpath(filepath, vault_dir)
                stale_items.append({
                    "filepath": rel_path,
                    "title": title,
                    "age_days": age_days,
                })

        except Exception as e:
            logger.error(f"Error scanning {filepath}: {e}")

    # Sort oldest first
    stale_items.sort(key=lambda x: x["age_days"], reverse=True)
    return stale_items


def format_bankruptcy_message(stale_items: list[dict]) -> str:
    """Format the user-facing bankruptcy prompt."""
    if not stale_items:
        return "✅ No stale reading items. Your queue is clean."

    count = len(stale_items)
    lines = [f"📚 You have **{count}** reading item{'s' if count != 1 else ''} older than 90 days:\n"]

    for item in stale_items:
        lines.append(f"  • `{item['filepath']}` — {item['title']} ({item['age_days']}d)")

    lines.append("")
    lines.append("Reply `/archive_reading` to move them to 4-Archives/, or `/keep` to retain.")

    return "\n".join(lines)


def update_frontmatter_date(filepath: str, new_date: date | None = None) -> str:
    """Update the date: field in a file's YAML frontmatter to reset the stale clock."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        target_date = (new_date or date.today()).isoformat()

        # Replace existing date in frontmatter
        updated = re.sub(
            r'(^---\s*\n(?:.*?\n)*?)date:\s*\S+',
            rf'\g<1>date: {target_date}',
            content,
            count=1,
            flags=re.DOTALL,
        )

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(updated)

        return f"Updated date to {target_date} in {filepath}"
    except Exception as e:
        return f"Error updating date in {filepath}: {e}"
