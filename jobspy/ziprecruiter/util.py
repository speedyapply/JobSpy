from __future__ import annotations

import base64
import json
import re
from urllib.parse import parse_qs, urlsplit


def page_values(html: str, *keys: str) -> list:
    """Values of `keys` in the data the page embeds for its JavaScript."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html)
    data = "".join(json.loads(chunk) for chunk in chunks)
    texts = _text_rows(data)

    def fill(obj: dict) -> dict:
        # "$2a" is text row 2a; a leading "$" is doubled
        for name, value in obj.items():
            if isinstance(value, str) and value.startswith("$"):
                text = value[1:] if value.startswith("$$") else value
                obj[name] = texts.get(value, text)
        return obj

    decoder = json.JSONDecoder(object_hook=fill)
    values = []
    for key in keys:
        start = data.find(f'"{key}":')
        if start == -1:
            raise ValueError(f"no {key} in the page")
        values.append(decoder.raw_decode(data, start + len(key) + 3)[0])
    return values


def _text_rows(data: str) -> dict[str, str]:
    """Long strings are rows: `2a:T<hex byte length>,<text>`, no newline after."""
    raw, texts, pos = data.encode(), {}, 0
    row = re.compile(rb"([0-9a-f]*):(?:T([0-9a-f]+),)?")
    while match := row.match(raw, pos):
        if match[2]:
            pos = match.end() + int(match[2], 16)
            texts[f"${match[1].decode()}"] = raw[match.end() : pos].decode()
        else:
            pos = raw.find(b"\n", pos) + 1 or len(raw)
    return texts


def direct_url(redirect_url: str) -> str | None:
    """The employer's link: a length-prefixed string in the redirect token."""
    try:
        token = parse_qs(urlsplit(redirect_url).query)["match_token"][0]
        fields = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        start = re.search(rb"https?://", fields).start()
        length = fields[start - 1]
        if fields[start - 2] >= 0x80:  # a length over 127 takes two bytes
            length = fields[start - 2] - 0x80 + length * 0x80
        url = fields[start : start + length].decode()
        # some trackers reject an unfilled "[click_id]"
        return re.sub(r"\[\w+\]", "", url)
    except Exception:
        return None
