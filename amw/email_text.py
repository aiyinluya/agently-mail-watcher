from __future__ import annotations

import html
import re


def html_to_plain(text: str) -> str:
    if not text:
        return ""
    # Drop script/style blocks
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def normalize_mail_body(raw: str, *, max_chars: int = 1500) -> str:
    plain = html_to_plain(raw)
    # Drop quoted reply chains (common in enterprise mail)
    for marker in (
        "写道：",
        "wrote:",
        "Original Message",
        "-----Original Message-----",
        "lizhuo7227@agent.qq.com",
        "广联达科技股份有限公司",
        "mailplugin_quote",
    ):
        idx = plain.find(marker)
        if idx > 0:
            plain = plain[:idx].strip()
    # First non-empty lines often hold the actual user request
    lines = [ln.strip() for ln in plain.splitlines() if ln.strip()]
    if lines:
        head = []
        for ln in lines:
            if any(x in ln for x in ("广联达", "高级软件", "@glodon.com", "@agent.qq.com")):
                break
            head.append(ln)
        if head:
            plain = "\n".join(head)
    if len(plain) > max_chars:
        plain = plain[: max_chars - 20].rstrip() + "\n…(正文已截断)"
    return plain
