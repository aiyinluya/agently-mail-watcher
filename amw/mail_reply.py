from __future__ import annotations

from typing import Any

from amw.agently import run_agently


def send_reply_email(
    *,
    to: list[str],
    subject: str,
    body: str,
    config: dict[str, Any] | None = None,
) -> Any:
    preview_args = ["message", "+send", "--subject", subject, "--body", body]
    for addr in to:
        preview_args.extend(["--to", addr])

    preview = run_agently(preview_args, config)
    token = None
    if isinstance(preview, dict):
        token = (
            preview.get("confirmation_token")
            or (preview.get("data") or {}).get("confirmation_token")
            or preview.get("confirmationToken")
        )
    if not token:
        raise RuntimeError("agently-cli +send did not return confirmation_token")

    send_args = preview_args + ["--confirmation-token", token]
    return run_agently(send_args, config)
