from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .lingualeo_client import DEFAULT_CDP_URL, LingualeoClient
from .models import BatchReport
from .parser import parse_entries, parse_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="AutoLeo",
        description="Add English definitions to a Lingualeo word set through an authorized Chrome session.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="UTF-8 text file with lines like: word — definition. If omitted, stdin is used.",
    )
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL, help="Chrome remote debugging URL.")
    parser.add_argument("--word-set-id", type=int, required=True, help="Lingualeo word set id.")
    parser.add_argument("--word-set-name", default="", help="Lingualeo word set name.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse the input and print words without changing Lingualeo.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        entries = parse_file(args.input) if args.input else parse_entries(sys.stdin.read())
    except Exception as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"Parsed {len(entries)} words:")
        for entry in entries:
            print(f"- {entry.word} — {entry.definition}")
        return 0

    print(f"AutoLeo: processing {len(entries)} words into {args.word_set_name} ({args.word_set_id})")
    print(f"Chrome: {args.cdp_url}")

    results = []
    try:
        with LingualeoClient(
            cdp_url=args.cdp_url,
            word_set_id=args.word_set_id,
            word_set_name=args.word_set_name,
        ) as client:
            for index, entry in enumerate(entries, start=1):
                result = client.process_entry(entry)
                results.append(result)
                status = "ok" if result.ok else "failed"
                print(f"[{index}/{len(entries)}] {status}: {entry.word} ({result.action.value})")
                if result.error:
                    print(f"    {result.error}")
            client.refresh_dictionary_page()
            print("Lingualeo page refreshed.")
    except Exception as exc:
        print(f"Connection error: {exc}", file=sys.stderr)
        print(
            "Open Chrome with --remote-debugging-port=9223, log in to Lingualeo manually, "
            "then run AutoLeo again.",
            file=sys.stderr,
        )
        return 1

    report = BatchReport(results)
    print()
    print("Report:")
    print(f"- added: {len(report.added)}")
    print(f"- updated: {len(report.updated)}")
    print(f"- already ok: {len(report.already_ok)}")
    print(f"- reset status: {report.reset_status_count}")
    print(f"- failed: {len(report.failed)}")

    if report.failed:
        print()
        print("Failed words:")
        for item in report.failed:
            reason = item.error or "verification failed"
            print(f"- {item.entry.word}: {reason}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
