"""Command-line interface.

  shipment-decision score <shipment.json> [--priority P] [--text]
  shipment-decision show <SHIPMENT_ID> [--out PATH]   # print/write a corpus shipment as JSON
  shipment-decision evaluate [--json PATH] [--markdown PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from shipment_decision.constants import PRIORITIES
from shipment_decision.corpus import get_shipment, strip_meta
from shipment_decision.evaluate import render_markdown, run_evaluation
from shipment_decision.pipeline import decide


def _cmd_score(args: argparse.Namespace) -> int:
    # utf-8-sig tolerates a UTF-8 BOM, which Windows editors and PowerShell often write.
    data = json.loads(Path(args.shipment).read_text(encoding="utf-8-sig"))
    if args.priority:
        if isinstance(data, dict):
            data["priority"] = args.priority
    result = decide(data)
    if args.text:
        print(result["explanation"])
    else:
        print(json.dumps(result, indent=2))
    return 0 if result["status"] != "invalid_input" else 2


def _cmd_show(args: argparse.Namespace) -> int:
    try:
        shipment = strip_meta(get_shipment(args.shipment_id))
    except KeyError:
        print(f"unknown corpus shipment {args.shipment_id}", file=sys.stderr)
        return 1
    text = json.dumps(shipment, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    report = run_evaluation()
    md = render_markdown(report)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.markdown:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text(md, encoding="utf-8")
    if not args.json and not args.markdown:
        print(md)
    else:
        print(f"wrote {args.json or ''} {args.markdown or ''}".strip())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="shipment-decision",
                                description="Recommend and explain a shipment route among supplied options.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("score", help="score one shipment JSON file")
    s.add_argument("shipment", help="path to shipment JSON")
    s.add_argument("--priority", choices=PRIORITIES, help="override the priority field before validation")
    s.add_argument("--text", action="store_true", help="print only the operator explanation")
    s.set_defaults(func=_cmd_score)

    w = sub.add_parser("show", help="print a corpus shipment (S01-S20, X01-X04) as JSON")
    w.add_argument("shipment_id")
    w.add_argument("--out", help="write the shipment JSON to this path instead of stdout")
    w.set_defaults(func=_cmd_show)

    e = sub.add_parser("evaluate", help="run the corpus evaluation and sensitivity experiments")
    e.add_argument("--json", help="write the full report as JSON to this path")
    e.add_argument("--markdown", help="write the summary as Markdown to this path")
    e.set_defaults(func=_cmd_evaluate)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
