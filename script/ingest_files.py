#!/usr/bin/env python3
"""Ingesta um ou mais arquivos diretamente no OpenSearch (sem passar pela fila).

O doc_id é extraído do nome do arquivo, garantindo que re-ingestar o mesmo
arquivo substitui os chunks antigos.

Exemplos:
  python script/ingest_files.py documents/contrato-acme.txt
  python script/ingest_files.py documents/manual.txt documents/politica-rh.txt
  python script/ingest_files.py documents/*.txt
  python script/ingest_files.py documents/contrato.txt --dry-run
  python script/ingest_files.py --debug-count
  python script/ingest_files.py --reset-index
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Adiciona shared/ e ingest_worker/ ao path (simula Lambda layer local)
_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root / "shared"))
sys.path.insert(0, str(_root / "ingest_worker"))

SUPPORTED_EXTENSIONS = {".txt", ".md"}


def _require_env() -> None:
    missing = [v for v in ("OPENSEARCH_ENDPOINT", "OPENSEARCH_INDEX") if not os.environ.get(v)]
    if missing:
        print(f"ERRO: variáveis de ambiente não configuradas: {', '.join(missing)}", file=sys.stderr)
        print("Dica: copie example.env.local.json e exporte as variáveis antes de rodar.", file=sys.stderr)
        sys.exit(1)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Ingesta arquivos no OpenSearch usando o nome do arquivo como doc_id."
    )
    p.add_argument("files", nargs="*", help="Arquivos a ingestar (um ou mais)")
    p.add_argument("--chunk-size", type=int, default=800, help="Tamanho do chunk em caracteres (default: 800)")
    p.add_argument("--encoding", default="utf-8", help="Encoding dos arquivos (default: utf-8)")
    p.add_argument("--dry-run", action="store_true", help="Mostra o que seria enviado sem indexar")
    p.add_argument("--debug-count", action="store_true", help="Mostra quantos documentos estão indexados")
    p.add_argument("--reset-index", action="store_true", help="Apaga e recria o índice no OpenSearch")
    return p


def _read_file(path: Path, encoding: str) -> str:
    if path.suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Formato não suportado: '{path.suffix}'. "
            f"Suportados: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return path.read_text(encoding=encoding)


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)

    if args.debug_count:
        _require_env()
        from opensearch import count_docs
        index = os.environ["OPENSEARCH_INDEX"]
        result = count_docs(index)
        print(f"Índice '{index}': {result['count']} documento(s) indexado(s)")
        return 0

    if args.reset_index:
        _require_env()
        from opensearch import reset_index
        index = os.environ["OPENSEARCH_INDEX"]
        confirm = input(f"Isso apaga todos os dados do índice '{index}'. Confirma? [s/N] ")
        if confirm.strip().lower() != "s":
            print("Cancelado.")
            return 0
        reset_index(index)
        print(f"Índice '{index}' recriado.")
        return 0

    if not args.files:
        print("Informe ao menos um arquivo. Use --help para ver as opções.", file=sys.stderr)
        return 1

    if not args.dry_run:
        _require_env()
        from app import process_job

    has_error = False

    for file_arg in args.files:
        path = Path(file_arg)
        doc_id = path.stem

        print(f"\n{'─' * 50}")
        print(f"Arquivo : {path}")
        print(f"doc_id  : {doc_id}")

        if not path.exists():
            print("ERRO    : arquivo não encontrado", file=sys.stderr)
            has_error = True
            continue

        try:
            text = _read_file(path, args.encoding)
        except ValueError as e:
            print(f"ERRO    : {e}", file=sys.stderr)
            has_error = True
            continue

        chunks_aprox = len(text) // args.chunk_size + 1
        print(f"Tamanho : {len(text):,} caracteres")
        print(f"Chunks  : ~{chunks_aprox} (chunk_size={args.chunk_size})")

        if args.dry_run:
            print("dry-run : nada indexado")
            continue

        try:
            result = process_job({
                "doc_id": doc_id,
                "text": text,
                "chunk_size": args.chunk_size,
                "persist": True,
                "embed": True,
            })
            print(f"Chunks  : {result['chunks']} indexados")
            print(f"Limpeza : {result['clean'].get('deleted', 0)} chunk(s) antigo(s) removidos")
            print(f"Bulk    : erros={result['bulk']['errors']}")
        except Exception as e:
            print(f"ERRO    : {e}", file=sys.stderr)
            has_error = True

    print(f"\n{'─' * 50}")
    total = len(args.files)
    print(f"Concluído: {total - int(has_error)}/{total} arquivo(s) processado(s) com sucesso")
    return 1 if has_error else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
