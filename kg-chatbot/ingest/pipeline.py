"""
Pipeline de ingesta del codebase hacia Neo4j via AST parsing.

Uso:
    python -m ingest.pipeline ./ruta/al/codebase

Para empezar desde cero en Neo4j, la pipeline limpia el grafo antes de ingestar.
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
    print(f"\n[ingesta] Directorio: {directory}")

    root = Path(directory).resolve()
    if not root.exists():
        print(f"[error] El directorio no existe: {root}")
        return

    files = list(walk_files(str(root)))
    total = len(files)
    if total == 0:
        print("[aviso] No se encontraron archivos .py compatibles.")
        return

    ckpt_path = _checkpoint_path(str(root))
    done_paths = _load_checkpoint(ckpt_path)
    pending = [f for f in files if str(f.relative_to(root)).replace("\\", "/") not in done_paths]

    if done_paths:
        print(f"[checkpoint] {len(done_paths)} archivos ya procesados, retomando...")
    print(f"[ingesta] {len(pending)} archivos pendientes de {total} totales.\n")

    if not pending:
        print("[ingesta] Nada nuevo que procesar. Grafo ya está actualizado.")
        return

    driver = get_neo4j_driver()

    # Limpiar grafo solo en ingesta completa (no en retoma de checkpoint)
    if not done_paths:
        print("[ingesta] Limpiando grafo existente...")
        clear_graph(driver)

    ingested = 0
    try:
        with driver.session() as session:
            for path in pending:
                rel = str(path.relative_to(root)).replace("\\", "/")
                data = parse_module(path, root)
                if data is None:
                    print(f"  [skip] {rel} (error de sintaxis o lectura)")
                    done_paths.add(rel)
                    continue

                write_parsed_module(session, data)
                done_paths.add(rel)
                ingested += 1
                print(f"  [{ingested}/{len(pending)}] {rel}")

                # Checkpoint cada 20 archivos
                if ingested % 20 == 0:
                    _save_checkpoint(ckpt_path, done_paths)

    except Exception as exc:
        _save_checkpoint(ckpt_path, done_paths)
        print(f"\n[error] {exc}")
        print(f"  Checkpoint guardado: {ckpt_path}")
        print(f"  Vuelve a ejecutar el mismo comando para retomar.")
        driver.close()
        return

    _save_checkpoint(ckpt_path, done_paths)
    driver.close()
    print(f"\n[ingesta] Completada. {ingested} archivos procesados.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m ingest.pipeline <directorio>")
        sys.exit(1)

    logging.basicConfig(level=logging.WARNING)
    asyncio.run(run_ingestion(sys.argv[1]))
