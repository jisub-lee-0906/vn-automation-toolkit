from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path


DB_CANDIDATE_NAMES = (
    'danbooru-taxonomy.release.sqlite',
    'danbooru-taxonomy.sqlite',
    'danbooru.sqlite',
)


@dataclass(frozen=True)
class TaxonomyHit:
    token: str
    tag: str
    source: str
    category: str = ''
    post_count: int | None = None
    match: str = ''


def normalize_tag(value: str | None) -> str:
    return (value or '').strip().lower().replace(' ', '_')


def find_taxonomy_db(workflow_root: Path) -> Path | None:
    for name in DB_CANDIDATE_NAMES:
        path = workflow_root / name
        if path.exists() and path.is_file():
            return path
    return None


def _sqlite_has_tags(db_path: Path) -> bool:
    try:
        with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as conn:
            conn.execute('PRAGMA query_only = ON')
            return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tags'").fetchone() is not None
    except sqlite3.Error:
        return False


def _lookup_sqlite(db_path: Path, token: str) -> TaxonomyHit | None:
    token_key = normalize_tag(token)
    token_display = token_key.replace('_', ' ')
    with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only = ON')
        row = conn.execute(
            """
            SELECT name, category_name, post_count, 'db_exact' AS match
            FROM tags
            WHERE is_deprecated = 0
              AND (normalized_name = ? OR name = ? OR display_name = ?)
            ORDER BY post_count DESC, name ASC
            LIMIT 1
            """,
            [token_key, token_key, token_display],
        ).fetchone()
        if row is None:
            row = conn.execute(
                """
                SELECT t.name, t.category_name, t.post_count, 'db_alias' AS match
                FROM tag_aliases a
                JOIN tags t ON t.id = a.target_tag_id
                WHERE a.status = 'active'
                  AND t.is_deprecated = 0
                  AND a.alias_normalized_name = ?
                ORDER BY t.post_count DESC, t.name ASC
                LIMIT 1
                """,
                [token_key],
            ).fetchone()
    if row is None:
        return None
    return TaxonomyHit(
        token=token,
        tag=str(row['name']),
        source='db',
        category=str(row['category_name']),
        post_count=int(row['post_count']),
        match=str(row['match']),
    )


def _load_csv_index(csv_path: Path) -> dict[str, str]:
    index: dict[str, str] = {}
    with csv_path.open('r', encoding='utf-8-sig', errors='replace', newline='') as f:
        sample = f.read(4096)
        f.seek(0)
        header = next(csv.reader(sample.splitlines()[:1]), [])
        normalized_header = {h.strip().lower() for h in header}
        if {'tag', 'aliases'}.issubset(normalized_header):
            reader = csv.DictReader(f)
            for row in reader:
                tag = (row.get('tag') or '').strip()
                if not tag:
                    continue
                index[normalize_tag(tag)] = tag
                for alias in (row.get('aliases') or '').split(','):
                    alias = alias.strip()
                    if alias:
                        index.setdefault(normalize_tag(alias), tag)
        else:
            for row in csv.reader(f):
                for cell in row[:2]:
                    tag = cell.strip()
                    if tag:
                        index[normalize_tag(tag)] = tag
    return index


def validate_tags(workflow_root: Path, tokens: list[str]) -> tuple[dict[str, dict], dict]:
    """Validate Danbooru-style tokens against SQLite first, legacy CSV second.

    Returns (validation_by_token, oracle_metadata). Raises RuntimeError when any
    token is missing from every available oracle. Legacy flat CSV is retained
    only for old tests/packs; current VN workflow packs should resolve via DB.
    """
    normalized_tokens = [normalize_tag(t) for t in tokens if normalize_tag(t)]
    db_path = find_taxonomy_db(workflow_root)
    source = None
    validation: dict[str, dict] = {}

    if db_path and _sqlite_has_tags(db_path):
        source = 'db'
        missing: list[str] = []
        for token in normalized_tokens:
            hit = _lookup_sqlite(db_path, token)
            if hit is None:
                missing.append(token)
            else:
                validation[token] = {
                    'input': token,
                    'tag': hit.tag,
                    'source': hit.source,
                    'category': hit.category,
                    'post_count': hit.post_count,
                    'match': hit.match,
                }
        if missing:
            raise RuntimeError(f'SQLite tag validation failed for prompt tags: {missing}')
        return validation, {
            'taxonomy_source': source,
            'taxonomy_db_path': str(db_path),
            'legacy_csv_path': str(workflow_root / 'danbooru_tag.csv'),
            'legacy_csv_used': False,
        }

    csv_path = workflow_root / 'danbooru_tag.csv'
    if csv_path.exists():
        source = 'csv'
        index = _load_csv_index(csv_path)
        missing = []
        for token in normalized_tokens:
            tag = index.get(token)
            if not tag:
                missing.append(token)
            else:
                validation[token] = {'input': token, 'tag': tag, 'source': 'csv'}
        if missing:
            raise RuntimeError(f'Legacy CSV tag validation failed for prompt tags: {missing}')
        return validation, {
            'taxonomy_source': source,
            'taxonomy_db_path': None,
            'legacy_csv_path': str(csv_path),
            'legacy_csv_used': True,
        }

    raise RuntimeError(
        f'No Danbooru taxonomy oracle found under {workflow_root}; expected one of '
        f'{", ".join(DB_CANDIDATE_NAMES)} or legacy danbooru_tag.csv'
    )
