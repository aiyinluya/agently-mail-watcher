#!/usr/bin/env python3
"""Poll Agently Mail inbox for configured senders and enqueue local jobs."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from amw.actions import write_job_queue
from amw.agently import read_message, search_messages
from amw.email_text import normalize_mail_body
from amw.util import (
    acquire_lock,
    install_signal_handlers,
    load_json,
    log_line,
    release_lock,
    render_template,
    resolve_path,
    save_json,
    utc_now_iso,
)

ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Agently Mail Watcher")
    p.add_argument("--once", action="store_true", help="single poll")
    p.add_argument("--config", type=Path, default=ROOT / "config.json")
    return p.parse_args()


def get_message_id(msg: Any) -> str | None:
    if not isinstance(msg, dict):
        return None
    return msg.get("message_id") or msg.get("id")


def get_from(msg: Any) -> str:
    if not isinstance(msg, dict):
        return ""
    frm = msg.get("from")
    if isinstance(frm, str):
        return frm
    if isinstance(frm, dict):
        return frm.get("email") or frm.get("address") or ""
    return ""


def get_subject(msg: Any) -> str:
    return msg.get("subject", "") if isinstance(msg, dict) else ""


def get_body_text(detail: Any, config: dict[str, Any] | None = None) -> str:
    if not isinstance(detail, dict):
        return ""
    max_chars = int((config or {}).get("maxBodyChars") or 1500)
    for key in ("body_text", "body", "snippet", "preview"):
        val = detail.get(key)
        if isinstance(val, str) and val:
            return normalize_mail_body(val, max_chars=max_chars)
    return ""


def run_actions(config: dict[str, Any], base_dir: Path, job: dict[str, Any]) -> None:
    actions = config.get("actions") or {}
    vars_map = {
        "from": job["from"],
        "subject": job["subject"],
        "body": job["body"],
        "messageId": job["messageId"],
        "replyTo": config.get("replyTo") or "",
        "workspace": config.get("workspace") or "",
    }
    prompt = render_template(config.get("agentPromptTemplate") or "", vars_map)
    job_with_prompt = {**job, "prompt": prompt, "createdAt": utc_now_iso()}

    queue = actions.get("jobQueue") or {}
    if queue.get("enabled", True):
        dir_path = resolve_path(base_dir, queue.get("dir") or "./jobs/pending")
        if dir_path:
            write_job_queue(dir_path, job_with_prompt)
            log_line(
                base_dir / "logs",
                "watcher",
                f"notify new mail: {job['from']} — {job['subject']}",
            )

def poll_once(config: dict[str, Any], base_dir: Path, processed: set[str]) -> None:
    senders = config.get("watchFrom") or []
    if not senders:
        raise RuntimeError("config.watchFrom is empty — add at least one sender email")

    seen: set[str] = set()
    log_dir = base_dir / "logs"
    for from_addr in senders:
        items = search_messages(from_addr=from_addr, is_unread=True, limit=20, config=config)
        for item in items:
            msg_id = get_message_id(item)
            if not msg_id or msg_id in seen or msg_id in processed:
                continue
            seen.add(msg_id)

            subject = get_subject(item)
            subject_filter = config.get("subjectContains")
            if subject_filter and subject_filter not in subject:
                continue

            detail = read_message(msg_id, config)
            body = get_body_text(detail, config) or get_body_text(item, config)
            job = {
                "messageId": msg_id,
                "from": get_from(item) or get_from(detail) or from_addr,
                "subject": subject,
                "body": body,
                "receivedAt": utc_now_iso(),
            }
            run_actions(config, base_dir, job)
            processed.add(msg_id)
            log_line(log_dir, "watcher", f"triggered job {msg_id} from {job['from']}: {subject}")


def main() -> int:
    args = parse_args()
    base_dir = args.config.resolve().parent
    try:
        config = load_json(args.config)
    except FileNotFoundError:
        print(f"Missing {args.config}", file=sys.stderr)
        print("Copy config.example.json to config.json and edit watchFrom / replyTo.", file=sys.stderr)
        return 2

    state_file = resolve_path(base_dir, config.get("stateFile") or "./state.json")
    lock_file = resolve_path(base_dir, config.get("lockFile") or "./watcher.pid")
    interval = max(15, int(config.get("pollIntervalSeconds") or 60))
    log_dir = base_dir / "logs"

    state = {"processedMessageIds": []}
    if state_file and state_file.is_file():
        state = load_json(state_file)
    processed = set(state.get("processedMessageIds") or [])

    if not args.once and lock_file:
        acquire_lock(lock_file, "watcher")
        install_signal_handlers(lock_file)

    def save_state() -> None:
        if not state_file:
            return
        ids = list(processed)[-5000:]
        save_json(state_file, {"processedMessageIds": ids, "updatedAt": utc_now_iso()})

    def loop() -> None:
        try:
            poll_once(config, base_dir, processed)
            save_state()
        except Exception as exc:
            msg = str(exc)
            log_line(log_dir, "watcher", f"ERROR: {msg}")
            if "re-authenticate" in msg or "Authorization required" in msg:
                log_line(log_dir, "watcher", "Run: agently-cli auth login")

    log_line(log_dir, "watcher", "poll once" if args.once else f"watcher started (interval {interval}s)", echo=args.once)
    loop()
    if args.once:
        return 0

    while True:
        time.sleep(interval)
        loop()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
