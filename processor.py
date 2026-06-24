#!/usr/bin/env python3
"""Process pending mail jobs with local Cursor Agent CLI (no cloud Automation)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from amw.local_agent import AgentRunError, assert_agent_ready, run_local_agent
from amw.mail_reply import send_reply_email
from amw.util import (
    acquire_lock,
    install_signal_handlers,
    load_json,
    log_line,
    resolve_path,
    utc_now_iso,
)

ROOT = Path(__file__).resolve().parent


def _maybe_send_failure_email(
    config: dict[str, Any], job: dict[str, Any], error_text: str, log_dir: Path
) -> None:
    la = config.get("localAgent") or {}
    if not la.get("sendReplyEmail") or not config.get("replyTo"):
        return
    if not la.get("sendFailureEmail", True):
        return
    subject = f"[自动反馈-失败] {job['subject']}"
    body = "\n".join(
        [
            f"原邮件：{job['from']} / {job['subject']}",
            f"消息 ID：{job['messageId']}",
            "",
            "--- 任务执行失败 ---",
            error_text[:4000] or "(无错误详情)",
        ]
    )
    try:
        if la.get("autoConfirmEmail", True):
            send_reply_email(to=[config["replyTo"]], subject=subject, body=body, config=config)
            log_line(log_dir, "processor", f"failure email sent to {config['replyTo']}")
    except Exception as mail_exc:
        log_line(log_dir, "processor", f"failure email error: {mail_exc}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Agently Mail Processor")
    p.add_argument("--once", action="store_true")
    p.add_argument("--config", type=Path, default=ROOT / "config.json")
    return p.parse_args()


def list_pending(pending_dir: Path) -> list[str]:
    if not pending_dir.is_dir():
        return []
    return sorted(p.name for p in pending_dir.glob("*.json"))


def process_one_job(config: dict[str, Any], base_dir: Path) -> bool:
    queue = (config.get("actions") or {}).get("jobQueue") or {}
    pending_dir = resolve_path(base_dir, queue.get("dir") or "./jobs/pending")
    processing_dir = resolve_path(base_dir, queue.get("processingDir") or "./jobs/processing")
    done_dir = resolve_path(base_dir, queue.get("doneDir") or "./jobs/done")
    failed_dir = resolve_path(base_dir, queue.get("failedDir") or "./jobs/failed")
    log_dir = base_dir / "logs"

    if not pending_dir:
        return False
    pending = list_pending(pending_dir)
    if not pending:
        return False

    name = pending[0]
    src = pending_dir / name
    job = json.loads(src.read_text(encoding="utf-8"))

    assert processing_dir and done_dir and failed_dir
    processing_dir.mkdir(parents=True, exist_ok=True)
    processing = processing_dir / name
    src.rename(processing)

    la = config.get("localAgent") or {}
    if not la.get("enabled", True):
        processing.rename(pending_dir / name)
        raise RuntimeError("localAgent.enabled is false — enable it in config.json")

    log_line(log_dir, "processor", f"processing {job['messageId']}: {job['subject']}")

    output = ""
    exit_code = 0
    try:
        if la.get("checkLogin", True):
            assert_agent_ready(config)
        result = run_local_agent(
            config,
            prompt=job["prompt"],
            workspace=config.get("workspace") or "",
            message_id=job.get("messageId", ""),
        )
        output = result["output"]
        exit_code = result["exit_code"]
    except AgentRunError as exc:
        exit_code = exc.exit_code
        output = exc.output or str(exc)
        log_line(log_dir, "processor", f"agent failed {job['messageId']}: {output[:500]}")
        failed_dir.mkdir(parents=True, exist_ok=True)
        fail_path = failed_dir / name
        fail_path.write_text(
            json.dumps(
                {**job, "error": output, "failedAt": utc_now_iso()},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        processing.unlink(missing_ok=True)
        log_line(log_dir, "processor", f"notify failed: {job['subject']}")
        _maybe_send_failure_email(config, job, output, log_dir)
        return True

    finished: dict[str, Any] = {
        **job,
        "agentOutput": output,
        "finishedAt": utc_now_iso(),
        "exitCode": exit_code,
    }

    if la.get("sendReplyEmail") and config.get("replyTo"):
        subject = f"[自动反馈] {job['subject']}"
        body = "\n".join(
            [
                f"原邮件：{job['from']} / {job['subject']}",
                f"消息 ID：{job['messageId']}",
                "",
                "--- Agent 执行结果 ---",
                output or "(无文本输出)",
            ]
        )
        try:
            if la.get("autoConfirmEmail", True):
                send_reply_email(
                    to=[config["replyTo"]],
                    subject=subject,
                    body=body,
                    config=config,
                )
                finished["replySent"] = True
                finished["replyTo"] = config["replyTo"]
            else:
                finished["replyPending"] = True
                finished["replyDraft"] = {"to": config["replyTo"], "subject": subject, "body": body}
        except Exception as mail_exc:
            finished["replyError"] = str(mail_exc)
            log_line(log_dir, "processor", f"reply failed: {finished['replyError']}")

    done_dir.mkdir(parents=True, exist_ok=True)
    (done_dir / name).write_text(
        json.dumps(finished, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    processing.unlink(missing_ok=True)
    log_line(log_dir, "processor", f"done {job['messageId']}")
    log_line(log_dir, "processor", f"notify completed: {job['subject']}")
    return True


def main() -> int:
    args = parse_args()
    base_dir = args.config.resolve().parent
    config = load_json(args.config)
    lock_file = resolve_path(base_dir, config.get("processorLockFile") or "./processor.pid")
    interval = max(5, int(config.get("processorIntervalSeconds") or 10))
    log_dir = base_dir / "logs"

    if not args.once and lock_file:
        acquire_lock(lock_file, "processor")
        install_signal_handlers(lock_file)

    log_line(
        log_dir,
        "processor",
        "processor once" if args.once else f"processor started (interval {interval}s)",
        echo=args.once,
    )

    def tick() -> bool:
        try:
            return process_one_job(config, base_dir)
        except Exception as exc:
            log_line(log_dir, "processor", f"ERROR: {exc}")
            return False

    if args.once:
        tick()
        return 0

    while True:
        tick()
        time.sleep(interval)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
