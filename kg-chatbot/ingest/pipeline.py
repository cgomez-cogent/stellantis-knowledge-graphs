"""
Codebase ingestion pipeline to Neo4j via AST parsing.

Usage:
    python -m ingest.pipeline ./path/to/codebase

To start fresh in Neo4j, the pipeline clears the graph before ingesting.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

from graph.store import get_neo4j_driver
from ingest.ast_parser import parse_module
from ingest.graph_writer import clear_graph, write_parsed_module
from ingest.loaders import walk_files

logger = logging.getLogger(__name__)


def _checkpoint_path(directory: str) -> Path:
    safe_name = Path(directory).resolve().name
    return Path(".kg_cache") / f"checkpoint_{safe_name}.json"


def _load_checkpoint(path: Path) -> set[str]:
    if path.exists():
        try:
            return set(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def _save_checkpoint(path: Path, done: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(done), indent=2), encoding="utf-8")


async def run_ingestion(directory: str) -> None:
    print(f"\n[ingestion] Directory: {directory}")

    root = Path(directory).resolve()
    if not root.exists():
        print(f"[error] Directory does not exist: {root}")
        return

    files = list(walk_files(str(root)))
    total = len(files)
    if total == 0:
        print("[warning] No compatible .py files found.")
        return

    ckpt_path = _checkpoint_path(str(root))
    done_paths = _load_checkpoint(ckpt_path)
    pending = [f for f in files if str(f.relative_to(root)).replace("\\", "/") not in done_paths]

    if done_paths:
        print(f"[checkpoint] {len(done_paths)} files already processed, resuming...")
    print(f"[ingestion] {len(pending)} pending files out of {total} total.\n")

    if not pending:
        print("[ingestion] Nothing new to process. Graph is already up to date.")
        return

    driver = get_neo4j_driver()

    # Clear graph only on full ingestion (not when resuming from checkpoint)
    if not done_paths:
        print("[ingestion] Clearing existing graph...")
        clear_graph(driver)

    ingested = 0
    try:
        with driver.session() as session:
            for path in pending:
                rel = str(path.relative_to(root)).replace("\\", "/")
                data = parse_module(path, root)
                if data is None:
                    print(f"  [skip] {rel} (syntax or read error)")
                    done_paths.add(rel)
                    continue

                write_parsed_module(session, data)
                done_paths.add(rel)
                ingested += 1
                print(f"  [{ingested}/{len(pending)}] {rel}")

                # Checkpoint every 20 files
                if ingested % 20 == 0:
                    _save_checkpoint(ckpt_path, done_paths)

    except Exception as exc:
        _save_checkpoint(ckpt_path, done_paths)
        print(f"\n[error] {exc}")
        print(f"  Checkpoint saved: {ckpt_path}")
        print(f"  Re-run the same command to resume.")
        driver.close()
        return

    _save_checkpoint(ckpt_path, done_paths)
    driver.close()
    print(f"\n[ingestion] Completed. {ingested} files processed.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m ingest.pipeline <directory>")
        sys.exit(1)

    logging.basicConfig(level=logging.WARNING)
    asyncio.run(run_ingestion(sys.argv[1]))
