import base64
import gzip
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DASH = "https://chromiumdash.appspot.com"
ROOT = Path(__file__).resolve().parent
CACHE_LOCK = threading.Lock()
RETRY_CODES = frozenset({403, 429, 500, 502, 503})

SOURCES = {
    "desktop": {
        "entries": "chrome/browser/about_flags.cc",
        "names": [
            "base/base_switches.h",
            "chrome/browser/site_isolation/about_flags.h",
            "components/ui_devtools/switches.cc",
        ],
        "strings": [
            ("chrome/browser/flag_descriptions.h", False),
            ("chrome/browser/ui/tabs/tab_group_home/constants.cc", True),
            ("components/commerce/core/flag_descriptions.cc", True),
            ("components/contextual_tasks/public/features.cc", True),
            ("components/enterprise/net/core/flag_descriptions.cc", True),
            ("components/omnibox/common/omnibox_features.cc", True),
        ],
    },
    "ios": {
        "entries": "ios/chrome/browser/flags/about_flags.mm",
        "names": [],
        "strings": [
            ("ios/chrome/browser/flags/ios_chrome_flag_descriptions.h", False),
            ("components/commerce/core/flag_descriptions.cc", True),
            ("components/enterprise/net/core/flag_descriptions.cc", True),
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
        "tokens": {"kOsIos"},
    },
]

FEATURE_ENTRIES_RE = re.compile(
    r"\bkFeatureEntries\b[^=]*=\s*(?:std::to_array\s*<[^;{}]+>\s*)?\(?\s*\{",
    re.MULTILINE,
)
STRING_DECL_RE = re.compile(
    r"(?:inline\s+|static\s+|constexpr\s+|const\s+)*"
    r"char\s+(?P<name>k[A-Za-z0-9_]+)\s*\[\]\s*=\s*"
    r'(?P<value>(?:"(?:\\.|[^"\\])*"\s*)+);',
    re.MULTILINE,
)
LITERAL_RE = re.compile(r'"((?:[^"\\]|\\.)*)"', re.DOTALL)
IDENTIFIER_RE = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_]*::)*(k[A-Za-z0-9_]+)\s*$")
OS_RE = re.compile(r"\bkOs[A-Za-z]+\b")
FLAG_LITERAL_RE = re.compile(r'"([A-Za-z0-9][A-Za-z0-9._-]*)"')

HEX_DIGITS = "0123456789abcdefABCDEF"
SIMPLE_ESCAPES = {
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
    '"': '"',
    "'": "'",
    "?": "?",
}


def fetch(url: str) -> str:
    headers = {"User-Agent": "chromeflags", "Accept-Encoding": "gzip"}
    request = urllib.request.Request(url, headers=headers)
    attempt = 0

    while True:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    body = gzip.decompress(body)
                return body.decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            if attempt == 3 or error.code not in RETRY_CODES:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 3:
                raise
        attempt += 1
        time.sleep(3 * attempt)


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


def feature_entries(clean: str) -> str:
    match = FEATURE_ENTRIES_RE.search(clean)
    if not match:
        raise ValueError("kFeatureEntries initializer not found")

    start = match.end()
    depth = 1
    index = start

    while index < len(clean):
        char = clean[index]
        if char in ('"', "'"):
            quote = char
            index += 1
            while index < len(clean):
                if clean[index] == "\\":
                    index += 2
                    continue
                if clean[index] == quote:
                    index += 1
                    break
                index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return clean[start:index]
        index += 1

    raise ValueError("kFeatureEntries initializer is unterminated")


def split_top_level(text: str) -> list[str]:
    fields = []
    start = 0
    depth = {"(": 0, "[": 0, "{": 0}
    pairs = {")": "(", "]": "[", "}": "{"}
    total_depth = 0
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
            total_depth += 1
        elif char in pairs:
            opener = pairs[char]
            if depth[opener] == 0:
                raise ValueError(f"unbalanced delimiter {char}")
            depth[opener] -= 1
            total_depth -= 1
        elif char == "," and total_depth == 0:
            fields.append(text[start:index].strip())
            start = index + 1
        index += 1

    if quote is not None or total_depth != 0:
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


def flag_name(expression: str, names: dict[str, str]) -> str | None:
    match = FLAG_LITERAL_RE.fullmatch(expression)
    if match:
        return match.group(1)
    return names.get("".join(expression.split()).rpartition("::")[2])


def parse_entries(clean: str, names: dict[str, str]) -> dict[str, dict]:
    pool = dict(names)
    pool.update(parse_strings(clean))

    result: dict[str, dict] = {}
    unparsed = []

    for block in entry_blocks(feature_entries(clean)):
        fields = split_top_level(block)
        if len(fields) < 4:
            unparsed.append(block)
            continue

        os_tokens = set(OS_RE.findall(fields[3]))
        flag = flag_name(fields[0], pool)
        if flag is None or not os_tokens:
            unparsed.append(block)
            continue

        entry = result.get(flag)
        if entry is None:
            result[flag] = {
                "title_key": string_key(fields[1]),
                "desc_key": string_key(fields[2]),
                "os": os_tokens,
            }
        else:
            entry["os"] |= os_tokens

    if unparsed:
        details = "; ".join(" ".join(block.split())[:80] for block in unparsed)
        raise ValueError(f"unparsed flag entries: {details}")
    if not result:
        raise ValueError("no flag entries parsed from kFeatureEntries")
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
        if escape in SIMPLE_ESCAPES:
            flush_bytes()
            result.append(SIMPLE_ESCAPES[escape])
            index += 2
            continue

        if escape == "x":
            cursor = index + 2
            while cursor < len(value) and value[cursor] in HEX_DIGITS:
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
            if len(digits) == 4 and all(char in HEX_DIGITS for char in digits):
                codepoint = int(digits, 16)
                if 0xD800 <= codepoint <= 0xDBFF:
                    next_index = index + 6
                    if value[next_index:next_index + 2] == "\\u":
                        low_digits = value[next_index + 2:next_index + 6]
                        if len(low_digits) == 4 and all(
                            char in HEX_DIGITS for char in low_digits
                        ):
                            low_codepoint = int(low_digits, 16)
                            if 0xDC00 <= low_codepoint <= 0xDFFF:
                                codepoint = 0x10000 + (
                                    (codepoint - 0xD800) << 10
                                ) + (low_codepoint - 0xDC00)
                                flush_bytes()
                                result.append(chr(codepoint))
                                index = next_index + 6
                                continue
                flush_bytes()
                result.append("\ufffd" if 0xD800 <= codepoint <= 0xDFFF else chr(codepoint))
                index += 6
                continue

        if escape == "U":
            digits = value[index + 2:index + 10]
            if len(digits) == 8 and all(char in HEX_DIGITS for char in digits):
                codepoint = int(digits, 16)
                if codepoint <= 0x10FFFF and not 0xD800 <= codepoint <= 0xDFFF:
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


def parse_strings(clean: str) -> dict[str, str]:
    return {
        match.group("name"): "".join(
            decode_cpp_string(literal)
            for literal in LITERAL_RE.findall(match.group("value"))
        )
        for match in STRING_DECL_RE.finditer(clean)
    }


def fetch_chromium(path: str, version: str, optional: bool = False) -> str | None:
    url = f"https://chromium.googlesource.com/chromium/src/+show/{version}/{path}?format=TEXT"
    try:
        content = fetch(url)
    except urllib.error.HTTPError as error:
        if error.code == 404 and optional:
            return None
        raise

    try:
        return base64.b64decode("".join(content.split()), validate=True).decode("utf-8", "replace")
    except ValueError:
        if optional:
            return None
        raise ValueError(f"failed to decode base64 content from {url}")


def declarations(path: str, version: str, optional: bool, cache: dict) -> dict[str, str]:
    key = ("file", version, path)
    with CACHE_LOCK:
        cached = cache.get(key)
    if cached is None:
        content = fetch_chromium(path, version, optional)
        cached = {} if content is None else parse_strings(strip_cpp_comments(content))
        with CACHE_LOCK:
            cache[key] = cached
    return cached


def load_entries(version: str, source: str, cache: dict) -> dict[str, dict]:
    key = ("entries", version, source)
    with CACHE_LOCK:
        if key in cache:
            return cache[key]

    group = SOURCES[source]
    names = {}
    for path in group["names"]:
        names.update(declarations(path, version, False, cache))
    clean = strip_cpp_comments(fetch_chromium(group["entries"], version))
    entries = parse_entries(clean, names)

    with CACHE_LOCK:
        cache[key] = entries
    return entries


def load_strings(version: str, source: str, cache: dict) -> dict[str, str]:
    result = {}
    for path, optional in SOURCES[source]["strings"]:
        result.update(declarations(path, version, optional, cache))
    return result


def number(version: str) -> tuple[int, ...]:
    parts = version.split(".")
    if len(parts) != 4 or not all(part.isdigit() for part in parts):
        raise ValueError(f"invalid Chrome version: {version}")
    return tuple(int(part) for part in parts)


def stable_milestone() -> int:
    data = json.loads(fetch(f"{DASH}/fetch_milestones?num=8"))
    current = [item["milestone"] for item in data if item.get("schedule_phase") == "stable"]
    if not current:
        raise ValueError("no milestone is in the Stable phase")
    return max(current)


def stable(platform: str) -> dict[int, str]:
    data = json.loads(fetch(f"{DASH}/fetch_releases?channel=Stable&platform={platform}&num=60"))
    releases = {}
    for item in data:
        version = item.get("version")
        if not version:
            continue
        try:
            parsed = number(version)
        except ValueError:
            continue
        milestone = parsed[0]
        if milestone not in releases or parsed > number(releases[milestone]):
            releases[milestone] = version
    return releases


def select(entries: dict[str, dict], tokens: set[str]) -> dict[str, dict]:
    return {flag: entry for flag, entry in entries.items() if entry["os"] & tokens}


def escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def describe(flag: str, entry: dict, strings: dict) -> tuple[str, str]:
    title = strings.get(entry["title_key"])
    desc = strings.get(entry["desc_key"])
    if title is None:
        print(f"warning: missing title string {entry['title_key']} for {flag}", file=sys.stderr)
        title = entry["title_key"]
    if desc is None:
        print(f"warning: missing description string {entry['desc_key']} for {flag}", file=sys.stderr)
        desc = entry["desc_key"]
    return title, desc


def report(platform: str, version: str, strings: dict, added: dict[str, dict]) -> str:
    lines = [f"# {platform} {version}", ""]
    if not added:
        lines.append("This release added no new flags.")
    for position, (flag, entry) in enumerate(added.items()):
        if position:
            lines.extend(["---", ""])
        title, body = describe(flag, entry, strings)
        lines.extend([
            f"**{escape(title)}**",
            "",
            escape(body),
            "",
            f"`chrome://flags/#{flag}`",
            "",
        ])
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> None:
    force = "--force" in sys.argv
    cache = {}
    summary = []

    with ThreadPoolExecutor(max_workers=len(PLATFORMS) + 1) as executor:
        current = executor.submit(stable_milestone)
        releases = {
            platform["name"]: executor.submit(
                stable, platform.get("dash", platform["name"])
            )
            for platform in PLATFORMS
        }
        releases = {name: future.result() for name, future in releases.items()}
        current = current.result()

    pending = []
    entry_tasks = set()
    string_tasks = set()

    for platform in PLATFORMS:
        name = platform["name"]
        newest = releases[name]

        released = [item for item in newest if item <= current]
        if not released:
            raise ValueError(f"no Stable release at or below milestone {current} for {name}")

        milestone = max(released)
        version = newest[milestone]
        baseline_milestone = milestone - 1

        while baseline_milestone not in newest and baseline_milestone > milestone - 8:
            baseline_milestone -= 1
        if baseline_milestone not in newest:
            raise ValueError(
                f"no earlier Stable release to compare {version} against for {name}"
            )

        baseline = newest[baseline_milestone]
        destination = ROOT / f"{name} {version}.md"
        stale = [path for path in ROOT.glob(f"{name} *.md") if path != destination]

        if not force and destination.exists() and not stale:
            continue

        source = platform["source"]
        pending.append((platform, version, baseline, destination, stale))
        entry_tasks.update({(version, source), (baseline, source)})
        string_tasks.add((version, source))

    if not pending:
        print("no flag changes")
        return

    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(load_entries, version, source, cache)
            for version, source in sorted(entry_tasks)
        ] + [
            executor.submit(load_strings, version, source, cache)
            for version, source in sorted(string_tasks)
        ]
        for future in futures:
            future.result()

    for platform, version, baseline, destination, stale in pending:
        name = platform["name"]
        source = platform["source"]
        tokens = platform["tokens"]

        selected = select(load_entries(version, source, cache), tokens)
        previous = select(load_entries(baseline, source, cache), tokens)
        added = {flag: selected[flag] for flag in sorted(set(selected) - set(previous))}

        document = report(name, version, load_strings(version, source, cache), added)

        if destination.exists() and not stale:
            if destination.read_text(encoding="utf-8") == document:
                continue

        for path in stale:
            path.unlink()
        destination.write_text(document, encoding="utf-8")
        summary.append(f"{name} {version} +{len(added)}")

    print(" / ".join(summary) or "no flag changes")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise
