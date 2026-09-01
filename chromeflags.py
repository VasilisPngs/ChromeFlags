import base64
import binascii
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DASH = "https://chromiumdash.appspot.com/fetch_releases"
RAW = "https://raw.githubusercontent.com/chromium/chromium"
GITHUB_API = "https://api.github.com/repos/chromium/chromium/contents"
ROOT = Path(__file__).resolve().parent

SOURCES = {
    "desktop": {
        "entries": "chrome/browser/about_flags.cc",
        "strings": [
            ("chrome/browser/flag_descriptions.h", False),
            ("components/commerce/core/flag_descriptions.cc", True),
            ("components/contextual_tasks/public/features.cc", True),
            ("components/enterprise/net/core/flag_descriptions.cc", True),
            ("components/omnibox/common/omnibox_features.cc", True),
        ],
    },
    "ios": {
        "entries": "ios/chrome/browser/flags/about_flags.mm",
        "strings": [
            ("ios/chrome/browser/flags/ios_chrome_flag_descriptions.h", False),
        ],
    },
}

PLATFORMS = [
    {
        "name": "Windows",
        "source": "desktop",
        "tokens": {"kOsWin", "kOsAll", "kOsDesktop", "kOsAura"},
    },
    {
        "name": "macOS",
        "dash": "Mac",
        "source": "desktop",
        "tokens": {"kOsMac", "kOsAll", "kOsDesktop"},
    },
    {
        "name": "Linux",
        "source": "desktop",
        "tokens": {"kOsLinux", "kOsAll", "kOsDesktop", "kOsAura"},
    },
    {
        "name": "Android",
        "source": "desktop",
        "tokens": {"kOsAndroid", "kOsAll"},
    },
    {
        "name": "iOS-iPadOS",
        "dash": "iOS",
        "source": "ios",
        "tokens": {"kOsIos", "kOsAll"},
    },
]

FEATURE_ENTRIES_RE = re.compile(
    r"\bkFeatureEntries\b[^=]*=\s*(?:std::to_array\s*<[^;{}]+>\s*)?\(?\s*\{",
    re.MULTILINE,
)
STRING_DECL_RE = re.compile(
    r"(?:inline\s+|static\s+|constexpr\s+|const\s+)*"
    r"char\s+(?P<name>k[A-Za-z0-9_]+)\s*\[\]\s*=\s*"
    r"(?P<value>(?:\"(?:\\.|[^\"\\])*\"\s*)+);",
    re.MULTILINE,
)
LITERAL_RE = re.compile(r'"((?:[^"\\]|\\.)*)"', re.DOTALL)
IDENTIFIER_RE = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_]*::)*(k[A-Za-z0-9_]+)\s*$")
OS_RE = re.compile(r"\bkOs[A-Za-z]+\b")


def fetch(url: str, optional: bool = False) -> str | None:
    headers = {"User-Agent": "chromeflags", "Accept-Encoding": "gzip"}
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                encoding = response.headers.get("Content-Encoding", "")
                if encoding.lower() == "gzip":
                    body = gzip.decompress(body)
                return body.decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            if error.code == 404 and optional:
                return None
            if error.code in (403, 429, 500, 502, 503) and attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"failed to fetch {url}")


def strip_cpp_comments(text: str) -> str:
    result = []
    index = 0
    length = len(text)
    state = "code"

    while index < length:
        char = text[index]
        next_char = text[index + 1] if index + 1 < length else ""

        if state == "code":
            if char == "/" and next_char == "/":
                state = "line_comment"
                result.append(" ")
                index += 2
                continue
            if char == "/" and next_char == "*":
                state = "block_comment"
                result.append(" ")
                index += 2
                continue
            if char == '"':
                state = "string"
            result.append(char)
            index += 1
            continue

        if state == "line_comment":
            if char == "\n":
                state = "code"
                result.append(char)
            else:
                result.append(" ")
            index += 1
            continue

        if state == "block_comment":
            if char == "*" and next_char == "/":
                state = "code"
                result.extend((" ", " "))
                index += 2
            else:
                result.append("\n" if char == "\n" else " ")
                index += 1
            continue

        result.append(char)
        if char == "\\" and index + 1 < length:
            result.append(text[index + 1])
            index += 2
        elif char == '"':
            state = "code"
            index += 1
        else:
            index += 1

    return "".join(result)


def feature_entries(text: str) -> str:
    clean_text = strip_cpp_comments(text)
    match = FEATURE_ENTRIES_RE.search(clean_text)
    if not match:
        raise ValueError("kFeatureEntries initializer not found")

    start = match.end()
    depth = 1
    index = start

    while index < len(clean_text):
        char = clean_text[index]
        if char in ('"', "'"):
            quote = char
            index += 1
            while index < len(clean_text):
                if clean_text[index] == "\\":
                    index += 2
                    continue
                if clean_text[index] == quote:
                    index += 1
                    break
                index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return clean_text[start:index]
        index += 1

    raise ValueError("kFeatureEntries initializer is unterminated")


def split_top_level(text: str, delimiter: str = ",") -> list[str]:
    fields = []
    start = 0
    depth = {"(": 0, "[": 0, "{": 0}
    pairs = {")": "(",
        "]": "[",
        "}": "{",
    }
    index = 0
    quote = None

    while index < len(text):
        char = text[index]
        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in ('"', "'"):
            quote = char
            index += 1
            continue
        if char in depth:
            depth[char] += 1
        elif char in pairs:
            opener = pairs[char]
            if depth[opener] == 0:
                raise ValueError(f"unbalanced delimiter {char}")
            depth[opener] -= 1
        elif char == delimiter and not any(depth.values()):
            fields.append(text[start:index].strip())
            start = index + 1
        index += 1

    if quote is not None or any(depth.values()):
        raise ValueError("unterminated entry field")
    fields.append(text[start:].strip())
    return fields


def entry_blocks(body: str) -> list[str]:
    blocks = []
    depth = 0
    start = None
    index = 0
    quote = None

    while index < len(body):
        char = body[index]
        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in ('"', "'"):
            quote = char
            index += 1
            continue
        if char == "{":
            if depth == 0:
                start = index + 1
            depth += 1
        elif char == "}":
            if depth == 0:
                raise ValueError("unexpected closing brace in flag entries")
            depth -= 1
            if depth == 0 and start is not None:
                blocks.append(body[start:index])
                start = None
        index += 1

    if quote is not None or depth != 0:
        raise ValueError("unterminated flag entry block")
    return blocks


def string_key(expression: str) -> str:
    match = IDENTIFIER_RE.search(expression.strip())
    if not match:
        raise ValueError(f"flag description key not found in expression: {expression}")
    return match.group(1)


def parse_entries(source: str) -> dict[str, dict]:
    body = feature_entries(source)
    result = {}

    for block in entry_blocks(body):
        fields = split_top_level(block)
        if len(fields) < 4:
            continue

        flag_match = re.fullmatch(r'"([A-Za-z0-9][A-Za-z0-9._-]*)"', fields[0])
        if not flag_match:
            continue

        flag = flag_match.group(1)
        title_key = string_key(fields[1])
        desc_key = string_key(fields[2])
        os_tokens = set(OS_RE.findall(fields[3]))
        if not os_tokens:
            continue

        result[flag] = {
            "title_key": title_key,
            "desc_key": desc_key,
            "os": os_tokens,
        }

    if not result:
        raise ValueError("no valid flag entries parsed from kFeatureEntries")
    return result


def decode_cpp_string(value: str) -> str:
    result = []
    byte_buffer = bytearray()

    def flush_bytes() -> None:
        if byte_buffer:
            result.append(bytes(byte_buffer).decode("utf-8", "replace"))
            byte_buffer.clear()

    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\":
            flush_bytes()
            result.append(char)
            index += 1
            continue

        if index + 1 >= len(value):
            result.append("\\")
            break

        escape = value[index + 1]
        simple = {
            "a": "\a",
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "v": "\v",
            "\\": "\\",
            "\"": "\"",
            "'": "'",
            "?": "?",
        }
        if escape in simple:
            flush_bytes()
            result.append(simple[escape])
            index += 2
            continue

        if escape == "x":
            cursor = index + 2
            while cursor < len(value) and value[cursor] in "0123456789abcdefABCDEF":
                cursor += 1
            if cursor == index + 2:
                flush_bytes()
                result.append("x")
                index += 2
            else:
                byte_buffer.append(int(value[index + 2:cursor], 16) & 0xFF)
                index = cursor
            continue

        if escape == "u":
            digits = value[index + 2:index + 6]
            if len(digits) == 4 and all(char in "0123456789abcdefABCDEF" for char in digits):
                flush_bytes()
                result.append(chr(int(digits, 16)))
                index += 6
                continue

        if escape == "U":
            digits = value[index + 2:index + 10]
            if len(digits) == 8 and all(char in "0123456789abcdefABCDEF" for char in digits):
                codepoint = int(digits, 16)
                if codepoint <= 0x10FFFF:
                    flush_bytes()
                    result.append(chr(codepoint))
                    index += 10
                    continue

        if escape in "01234567":
            cursor = index + 1
            while cursor < min(index + 4, len(value)) and value[cursor] in "01234567":
                cursor += 1
            byte_buffer.append(int(value[index + 1:cursor], 8) & 0xFF)
            index = cursor
            continue

        flush_bytes()
        result.append(escape)
        index += 2

    flush_bytes()
    return "".join(result)


def parse_strings(source: str) -> dict[str, str]:
    result = {}
    for match in STRING_DECL_RE.finditer(strip_cpp_comments(source)):
        literals = LITERAL_RE.findall(match.group("value"))
        result[match.group("name")] = "".join(
            decode_cpp_string(literal) for literal in literals
        )
    return result


def fetch_chromium(path: str, version: str, optional: bool = False) -> str | None:
    endpoints = (
        (
            f"https://chromium.googlesource.com/chromium/src/+show/{version}/{path}?format=TEXT",
            "gitiles",
        ),
        (f"{RAW}/{version}/{path}", "raw"),
        (f"{GITHUB_API}/{path}?ref={version}", "api"),
    )

    for url, kind in endpoints:
        try:
            content = fetch(url)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                continue
            raise

        if kind == "gitiles":
            encoded = "".join(content.split())
            try:
                return base64.b64decode(encoded, validate=True).decode("utf-8", "replace")
            except (ValueError, binascii.Error):
                continue

        if kind == "api":
            try:
                data = json.loads(content)
                encoded = data.get("content")
                if not isinstance(encoded, str):
                    continue
                return base64.b64decode("".join(encoded.split())).decode("utf-8", "replace")
            except (json.JSONDecodeError, ValueError, binascii.Error):
                continue

        return content

    if optional:
        return None
    raise FileNotFoundError(f"Chromium source not found: {path}@{version}")

def load(kind: str, version: str, source: str, cache: dict) -> dict:
    key = (kind, version, source)
    if key in cache:
        return cache[key]
    if source not in SOURCES:
        raise ValueError(f"unknown source group: {source}")

    if kind == "entries":
        path = SOURCES[source]["entries"]
        result = parse_entries(fetch_chromium(path, version))
    elif kind == "strings":
        result = {}
        for path, optional in SOURCES[source]["strings"]:
            file_key = ("string_file", version, path)
            parsed = cache.get(file_key)
            if parsed is None:
                text = fetch_chromium(path, version, optional)
                if text is None:
                    parsed = {}
                else:
                    parsed = parse_strings(text)
                    cache[file_key] = parsed
            result.update(parsed)
    else:
        raise ValueError(f"unknown data kind: {kind}")

    cache[key] = result
    return result

def load_strings_for_report(
    version: str,
    source: str,
    added: list[str],
    cache: dict,
) -> dict[str, str]:
    entries = load("entries", version, source, cache)
    result = {}
    for path, optional in SOURCES[source]["strings"]:
        file_key = ("string_file", version, path)
        parsed = cache.get(file_key)
        if parsed is None:
            text = fetch_chromium(path, version, optional)
            if text is None:
                parsed = {}
            else:
                parsed = parse_strings(text)
                cache[file_key] = parsed
        result.update(parsed)

    missing = {
        key
        for flag in added
        for key in (entries[flag]["title_key"], entries[flag]["desc_key"])
        if key not in result
    }
    if missing:
        raise ValueError(
            "missing Chromium flag strings: " + ", ".join(sorted(missing))
        )
    return result

def main() -> None:
    cache = {}
    title = []

    with ThreadPoolExecutor(max_workers=len(PLATFORMS)) as executor:
        release_futures = {
            platform["name"]: executor.submit(
                stable, platform.get("dash", platform["name"])
            )
            for platform in PLATFORMS
        }
        releases = {
            name: future.result()
            for name, future in release_futures.items()
        }

    platform_params = []
    load_tasks = set()

    for platform in PLATFORMS:
        name = platform["name"]
        newest = releases[name]
        if not newest:
            raise ValueError(f"no Stable releases listed for {name}")

        milestone = max(newest)
        version = newest[milestone]
        baseline_milestone = milestone - 1

        while baseline_milestone not in newest and baseline_milestone > milestone - 8:
            baseline_milestone -= 1
        if baseline_milestone not in newest:
            raise ValueError(
                f"no earlier Stable release to compare {version} against for {name}"
            )

        baseline = newest[baseline_milestone]
        source = platform["source"]
        platform_params.append((platform, version, baseline))
        load_tasks.add(("entries", version, source))
        load_tasks.add(("entries", baseline, source))

    for kind, version, source in sorted(load_tasks):
        load(kind, version, source, cache)

    for platform, version, baseline in platform_params:
        name = platform["name"]
        source = platform["source"]
        tokens = platform["tokens"]

        selected = select(load("entries", version, source, cache), tokens)
        previous = select(load("entries", baseline, source, cache), tokens)
        added = sorted(set(selected) - set(previous))

        document = report(
            name,
            version,
            load_strings_for_report(version, source, added, cache),
            selected,
            added,
        )
        destination = ROOT / f"{name} {version}.md"
        stale = [
            path
            for path in ROOT.glob(f"{name} *.md")
            if path != destination
        ]

        if destination.exists() and not stale:
            if destination.read_text(encoding="utf-8") == document:
                continue

        for path in stale:
            path.unlink()
        destination.write_text(document, encoding="utf-8")
        title.append(f"{name} {version} +{len(added)}")

    print(" / ".join(title) or "no flag changes")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise
