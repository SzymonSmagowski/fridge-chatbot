"""Push the chat-graph behavioral test matrix to a local Langfuse instance.

Reads either:
- a markdown file with a single GitHub-style table per section (the matrix
  format used in docs/features/chat-graph-test-matrix.md), OR
- a JSONL file with one object per line keyed by `id`.

Each row becomes a `DatasetItem` under the named dataset. Idempotent —
re-running with the same dataset name + same row `id` updates the existing
item rather than appending. The `id` column from the matrix is used as the
Langfuse `id` so external tools can cross-reference.

Usage:
    poetry run python scripts/langfuse_dataset.py push <matrix-file>           [--name NAME]
    poetry run python scripts/langfuse_dataset.py list
    poetry run python scripts/langfuse_dataset.py pull <name>                  [--out FILE]

Targets the local devcontainer Langfuse at LANGFUSE_HOST=http://langfuse-web:3000
with the dev keys wired into .env.example. Surface this UI at
http://localhost:3001 once the script reports success.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The langfuse v3 SDK reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY /
# LANGFUSE_HOST from the env directly. Surface a clear error if any is
# missing rather than letting the SDK do its own (less helpful) failure.
REQUIRED_ENV = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")


@dataclass
class MatrixRow:
    id: str
    tool: str
    category: str
    priority: str
    input: str
    expected_tool_calls: str
    expected_response_property: str
    expected_db_change: str
    section: str = ""
    extra: dict = field(default_factory=dict)

    def to_input(self) -> dict:
        return {"prompt": self.input}

    def to_expected(self) -> dict:
        return {
            "tool_calls": [
                t.strip()
                for t in self.expected_tool_calls.split(",")
                if t.strip()
            ],
            "response_property": self.expected_response_property,
            "db_change": self.expected_db_change,
        }

    def to_metadata(self) -> dict:
        return {
            "matrix_id": self.id,
            "tool": self.tool,
            "category": self.category,
            "priority": self.priority,
            "section": self.section,
            **self.extra,
        }


# ---------------------------------------------------------------------------
# Matrix parsers
# ---------------------------------------------------------------------------


_HEADER_PATTERN = re.compile(r"^##\s+(.+?)\s*$")
_TABLE_DIVIDER = re.compile(r"^\|[\s|:\-]+\|\s*$")


def parse_markdown_matrix(path: Path) -> list[MatrixRow]:
    """Parse a matrix-format markdown file.

    A row is any line inside a markdown table (`| ... |`) under a heading
    that starts with `## `. The schema row (header) is recognised by the
    `id` column name — anything before that is ignored.
    """
    rows: list[MatrixRow] = []
    section = ""
    headers: list[str] | None = None
    in_table = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()

        m = _HEADER_PATTERN.match(line)
        if m:
            section = m.group(1).strip()
            headers = None
            in_table = False
            continue

        if not line.strip().startswith("|"):
            in_table = False
            headers = None
            continue

        cells = [c.strip() for c in line.strip().strip("|").split("|")]

        if _TABLE_DIVIDER.match(line):
            # divider — keep table-mode, skip
            continue

        if headers is None:
            # candidate header row
            if "id" in [c.lower() for c in cells]:
                headers = [c.lower() for c in cells]
                in_table = True
            continue

        if not in_table:
            continue

        if len(cells) < len(headers):
            continue

        record = dict(zip(headers, cells))
        if not record.get("id") or record.get("id") == "id":
            continue

        rows.append(
            MatrixRow(
                id=record.get("id", ""),
                tool=record.get("tool", ""),
                category=record.get("category", ""),
                priority=record.get("priority", ""),
                input=record.get("input", ""),
                expected_tool_calls=record.get("expected_tool_calls", ""),
                expected_response_property=record.get(
                    "expected_response_property", ""
                ),
                expected_db_change=record.get("expected_db_change", ""),
                section=section,
            )
        )
    return rows


def parse_jsonl_matrix(path: Path) -> list[MatrixRow]:
    rows: list[MatrixRow] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        rows.append(
            MatrixRow(
                id=str(obj.get("id", "")),
                tool=obj.get("tool", ""),
                category=obj.get("category", ""),
                priority=obj.get("priority", ""),
                input=obj.get("input", ""),
                expected_tool_calls=obj.get("expected_tool_calls", ""),
                expected_response_property=obj.get(
                    "expected_response_property", ""
                ),
                expected_db_change=obj.get("expected_db_change", ""),
                section=obj.get("section", ""),
                extra={k: v for k, v in obj.items() if k not in MatrixRow.__annotations__},
            )
        )
    return rows


def load_matrix(path: Path) -> list[MatrixRow]:
    if path.suffix.lower() in (".jsonl", ".ndjson"):
        return parse_jsonl_matrix(path)
    return parse_markdown_matrix(path)


# ---------------------------------------------------------------------------
# Langfuse client + commands
# ---------------------------------------------------------------------------


def _check_env() -> None:
    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        sys.stderr.write(
            "Missing required env vars: "
            + ", ".join(missing)
            + "\nFor the local devcontainer, source apps/fridge-chatbot/backend/.env\n"
        )
        sys.exit(2)


def _client():
    _check_env()
    from langfuse import Langfuse

    return Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ["LANGFUSE_HOST"],
    )


def cmd_push(args: argparse.Namespace) -> int:
    rows = load_matrix(Path(args.matrix))
    if not rows:
        sys.stderr.write(f"No rows parsed from {args.matrix}\n")
        return 1

    name = args.name or "chat-graph-behavioral"
    description = args.description or (
        f"Behavioral test matrix for the chat graph; sourced from "
        f"{Path(args.matrix).name}"
    )

    lf = _client()

    # create_dataset is idempotent — calling with an existing name returns
    # the existing dataset rather than failing.
    lf.create_dataset(
        name=name,
        description=description,
        metadata={"source": str(args.matrix), "row_count": len(rows)},
    )

    pushed = 0
    for row in rows:
        lf.create_dataset_item(
            dataset_name=name,
            id=row.id,
            input=row.to_input(),
            expected_output=row.to_expected(),
            metadata=row.to_metadata(),
        )
        pushed += 1

    lf.flush()
    print(
        f"pushed {pushed} items to dataset '{name}' on {os.environ['LANGFUSE_HOST']}"
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    _check_env()
    # Langfuse v3 exposes get_dataset / get_dataset_items but no top-level
    # "list datasets" SDK method as of writing; fall back to the REST API.
    import urllib.parse
    import urllib.request
    import base64

    auth = base64.b64encode(
        f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}".encode()
    ).decode()
    url = urllib.parse.urljoin(os.environ["LANGFUSE_HOST"], "/api/public/datasets")
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read())

    items = body.get("data") or body.get("datasets") or []
    if not items:
        print("(no datasets)")
        return 0
    for d in items:
        n = d.get("name", "?")
        item_field = d.get("itemCount") or d.get("items") or 0
        c = len(item_field) if isinstance(item_field, list) else item_field
        print(f"  {n}  ({c} items)")
    return 0


def cmd_pull(args: argparse.Namespace) -> int:
    lf = _client()
    dataset = lf.get_dataset(args.name)
    out_path = Path(args.out) if args.out else Path(f"{args.name}.jsonl")
    with out_path.open("w", encoding="utf-8") as fh:
        for item in dataset.items:
            fh.write(
                json.dumps(
                    {
                        "id": item.id,
                        "input": item.input,
                        "expected_output": item.expected_output,
                        "metadata": item.metadata,
                    }
                )
                + "\n"
            )
    print(f"pulled {len(dataset.items)} items → {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langfuse_dataset")
    sub = parser.add_subparsers(dest="cmd", required=True)

    push = sub.add_parser("push", help="upload a matrix file as a dataset")
    push.add_argument("matrix", help="path to the matrix .md or .jsonl")
    push.add_argument("--name", help="dataset name (default: chat-graph-behavioral)")
    push.add_argument("--description", help="dataset description")
    push.set_defaults(func=cmd_push)

    lst = sub.add_parser("list", help="list datasets in the local Langfuse")
    lst.set_defaults(func=cmd_list)

    pull = sub.add_parser("pull", help="dump a dataset back to JSONL")
    pull.add_argument("name", help="dataset name to pull")
    pull.add_argument("--out", help="output path (default: <name>.jsonl)")
    pull.set_defaults(func=cmd_pull)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
