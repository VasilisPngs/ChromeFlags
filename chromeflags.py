import base64
import gzip
import http.client
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DASH = "https://chromiumdash.appspot.com"
ROOT = Path(__file__).resolve().parent
CACHE_LOCK = threading.Lock()
RETRY_CODES = frozenset({403, 429, 500, 502, 503})
TRANSIENT_ERRORS = (OSError, http.client.HTTPException, zlib.error, EOFError)

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

KNOWN_TOKENS = frozenset().union(
    {"kOsCrOS", "kOsCrOSOwnerOnly", "kOsFuchsia", "kOsWebView"},
    *(platform["tokens"] for platform in PLATFORMS),
)

UNEXPIRE_INCLUDE = '#include "chrome/browser/unexpire_flags_gen.inc"'
UNEXPIRE_GENERATOR = "tools/flags/generate_unexpire_flags.py"
UNEXPIRE_LOGIC = ("return [mstone - 1, mstone]", "gen_flags_fragment(progname, mstone - 1)")
UNEXPIRE_FRAGMENT = """
    {{"temporary-unexpire-flags-m{m}",
     "Temporarily unexpire M{m} flags.",
     "Temporarily unexpire flags that expired as of M{m}. These flags will be"
     " removed soon.",
     kOsAll | flags_ui::kFlagInfrastructure,
     FEATURE_VALUE_TYPE(flags::kUnexpireFlagsM{m})}},
"""

LITERALS = r'(?:"(?:\\.|[^"\\])*"\s*)+'
FEATURE_ENTRIES_RE = re.compile(
    r"\bkFeatureEntries\b[^=]*=\s*(?:std::to_array\s*<[^;{}]+>\s*)?\(?\s*\{"
)
STRING_DECL_RE = re.compile(rf"char\s+(?P<name>k[A-Za-z0-9_]+)\s*\[\]\s*=\s*(?P<value>{LITERALS});")
LITERALS_RE = re.compile(LITERALS)
LITERAL_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
IDENTIFIER_RE = re.compile(r"(k[A-Za-z0-9_]+)\s*$")
OS_RE = re.compile(r"\bkOs[A-Za-z]+\b")
FLAG_LITERAL_RE = re.compile(r'"([A-Za-z0-9][A-Za-z0-9._-]*)"')
DIRECTIVE_RE = re.compile(r"[ \t]*#[ \t]*(\w*)")
INCLUDE_RE = re.compile(r'[ \t]*#[ \t]*include[ \t]*["<]([^">]*)[">]')
TERMINATOR_RE = re.compile(r"\s*[;)]")

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
            error.close()
            if attempt == 3 or error.code not in RETRY_CODES:
                raise
        except TRANSIENT_ERRORS:
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


def unquoted(text: str) -> Iterator[tuple[int, str]]:
    index = 0
    while index < len(text):
        char = text[index]
        if char in ('"', "'"):
            index += 1
            while index < len(text) and text[index] != char:
                index += 2 if text[index] == "\\" else 1
            if index >= len(text):
                raise ValueError("unterminated literal")
        else:
            yield index, char
        index += 1


def branch(frames: list[list], word: str, depth: int) -> int:
    if word in ("if", "ifdef", "ifndef"):
        frames.append([depth, None, False])
    elif frames and word in ("elif", "elifdef", "elifndef", "else"):
        frame = frames[-1]
        if not frame[2]:
            frame[1:] = [depth, True]
        return frame[0]
    elif frames and word == "endif":
        frame = frames.pop()
        if frame[2]:
            return frame[1]
    return depth


def feature_entries(clean: str) -> str:
    match = FEATURE_ENTRIES_RE.search(clean)
    if not match:
        raise ValueError("kFeatureEntries initializer not found")

    kept = []
    frames = []
    depth = 1
    continued = False
    position = match.end()

    for line in clean[position:].split("\n"):
        directive = None if continued else DIRECTIVE_RE.match(line)
        if continued or directive:
            if directive:
                include = INCLUDE_RE.match(line)
                if include and not include.group(1).endswith(".h"):
                    raise ValueError(f"kFeatureEntries includes {include.group(1)}, which is not parsed")
                depth = branch(frames, directive.group(1), depth)
            continued = line.rstrip().endswith("\\")
        elif not any(frame[2] and frame[1] != frame[0] for frame in frames):
            for index, char in unquoted(line):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        end = position + index
                        if not TERMINATOR_RE.match(clean, end + 1):
                            line_number = clean.count("\n", 0, end) + 1
                            raise ValueError(f"kFeatureEntries initializer closes early on line {line_number}")
                        return "\n".join(kept + [line[:index]])
            kept.append(line)
        position += len(line) + 1

    raise ValueError("kFeatureEntries initializer is unterminated")


def split_top_level(text: str) -> list[str]:
    fields = []
    start = 0
    depth = {"(": 0, "[": 0, "{": 0}
    pairs = {")": "(", "]": "[", "}": "{"}

    for index, char in unquoted(text):
        if char in depth:
            depth[char] += 1
        elif char in pairs:
            if depth[pairs[char]] == 0:
                raise ValueError(f"unbalanced delimiter {char}")
            depth[pairs[char]] -= 1
        elif char == "," and not any(depth.values()):
            fields.append(text[start:index].strip())
            start = index + 1

    if any(depth.values()):
        raise ValueError("unterminated entry field")
    fields.append(text[start:].strip())
    return fields


def entry_blocks(body: str) -> list[str]:
    blocks = []
    depth = 0
    start = 0

    for index, char in unquoted(body):
        if char == "{":
            if depth == 0:
                start = index + 1
            depth += 1
        elif char == "}":
            if depth == 0:
                raise ValueError("unexpected closing brace in flag entries")
            depth -= 1
            if depth == 0:
                blocks.append(body[start:index])

    if depth:
        raise ValueError("unterminated flag entry block")
    return blocks


def string_key(expression: str) -> str:
    if LITERALS_RE.fullmatch(expression):
        return expression
    match = IDENTIFIER_RE.search(expression)
    if not match:
        raise ValueError(f"flag description key not found in expression: {expression}")
    return match.group(1)


def flag_name(expression: str, names: dict[str, str]) -> str | None:
    match = FLAG_LITERAL_RE.fullmatch(expression)
    if match:
        return match.group(1)
    return names.get("".join(expression.split()).rpartition("::")[2])


def parse_entries(clean: str, names: dict[str, str]) -> dict[str, list[dict]]:
    pool = dict(names)
    pool.update(parse_strings(clean))

    result: dict[str, list[dict]] = {}
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
        unknown = os_tokens - KNOWN_TOKENS
        if unknown:
            raise ValueError(f"{flag} uses unknown platform tokens: {', '.join(sorted(unknown))}")

        result.setdefault(flag, []).append({
            "title_key": string_key(fields[1]),
            "desc_key": string_key(fields[2]),
            "os": os_tokens,
        })

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


def literal_text(value: str) -> str:
    return "".join(decode_cpp_string(literal) for literal in LITERAL_RE.findall(value))


def parse_strings(clean: str) -> dict[str, str]:
    return {match.group("name"): literal_text(match.group("value")) for match in STRING_DECL_RE.finditer(clean)}


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


def expand_unexpire(clean: str, version: str) -> str:
    if UNEXPIRE_INCLUDE not in clean:
        return clean
    generator = fetch_chromium(UNEXPIRE_GENERATOR, version)
    if not all(part in generator for part in (UNEXPIRE_FRAGMENT, *UNEXPIRE_LOGIC)):
        raise ValueError(f"{UNEXPIRE_GENERATOR} no longer generates the expected unexpire flags")
    milestone = number(version)[0]
    fragment = "".join(UNEXPIRE_FRAGMENT.format(m=m) for m in (milestone - 2, milestone - 1))
    return clean.replace(UNEXPIRE_INCLUDE, fragment)


def load_entries(version: str, source: str, cache: dict) -> dict[str, list[dict]]:
    key = ("entries", version, source)
    with CACHE_LOCK:
        if key in cache:
            return cache[key]

    group = SOURCES[source]
    names = {}
    for path in group.get("names", ()):
        names.update(declarations(path, version, False, cache))
    clean = expand_unexpire(strip_cpp_comments(fetch_chromium(group["entries"], version)), version)
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


def stable(platform: str) -> dict[int, tuple[str, int]]:
    data = json.loads(fetch(f"{DASH}/fetch_releases?channel=Stable&platform={platform}&num=60"))
    releases: dict[int, tuple[str, int]] = {}
    for item in data:
        version = item.get("version")
        released = item.get("time")
        if not version:
            continue
        if not isinstance(released, (int, float)) or isinstance(released, bool):
            released = 0
        try:
            parsed = number(version)
        except ValueError:
            continue
        milestone = parsed[0]
        known = releases.get(milestone)
        if known is None or parsed > number(known[0]):
            releases[milestone] = (version, int(released))
    if not releases:
        raise ValueError("no Stable release listed")
    return releases


def stable_cap() -> int | None:
    try:
        data = json.loads(fetch(f"{DASH}/fetch_milestones?num=8"))
        settled = [
            item["milestone"]
            for item in data
            if item.get("schedule_phase") == "stable" and isinstance(item.get("milestone"), int)
        ]
    except Exception as error:
        print(f"warning: milestone phases unavailable: {error}", file=sys.stderr)
        return None
    return max(settled) if settled else None


def current_milestone(releases: dict[int, tuple[str, int]], cap: int | None) -> int:
    timed = len({released for _, released in releases.values()}) > 1
    for milestone in sorted(releases, reverse=True):
        if cap is not None and milestone <= cap:
            return milestone
        if timed and all(
            released < releases[milestone][1]
            for lower, (_, released) in releases.items()
            if lower < milestone
        ):
            return milestone
    return max(releases)


def select(entries: dict[str, list[dict]], tokens: set[str]) -> dict[str, dict]:
    selected = {}
    for flag, variants in entries.items():
        for variant in variants:
            if variant["os"] & tokens:
                selected[flag] = variant
                break
    return selected


def escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def resolve(key: str, strings: dict) -> str | None:
    return literal_text(key) if key.startswith('"') else strings.get(key)


def describe(flag: str, entry: dict, strings: dict) -> tuple[str, str]:
    title = resolve(entry["title_key"], strings)
    desc = resolve(entry["desc_key"], strings)
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


def finish(summary: list[str], skipped: list[str]) -> None:
    for note in skipped:
        print(f"warning: {note}", file=sys.stderr)
    if len(skipped) == len(PLATFORMS):
        raise RuntimeError("; ".join(skipped))
    line = " / ".join(summary) or "no flag changes"
    if skipped:
        line = f"{line} (skipped {len(skipped)})"
    print(line)


def main() -> None:
    force = "--force" in sys.argv
    cache = {}
    summary = []
    skipped = []

    with ThreadPoolExecutor(max_workers=len(PLATFORMS) + 1) as executor:
        cap = executor.submit(stable_cap)
        futures = {
            platform["name"]: executor.submit(
                stable, platform.get("dash", platform["name"])
            )
            for platform in PLATFORMS
        }
        releases = {}
        for name, future in futures.items():
            try:
                releases[name] = future.result()
            except Exception as error:
                skipped.append(f"{name}: {error}")
        cap = cap.result()

    pending = []
    entry_tasks = set()
    string_tasks = set()

    for platform in PLATFORMS:
        name = platform["name"]
        newest = releases.get(name)
        if newest is None:
            continue

        try:
            milestone = current_milestone(newest, cap)
            version = newest[milestone][0]
            baseline_milestone = milestone - 1

            while baseline_milestone not in newest and baseline_milestone > milestone - 8:
                baseline_milestone -= 1
            if baseline_milestone not in newest:
                raise ValueError(f"no earlier Stable release to compare {version} against")

            baseline = newest[baseline_milestone][0]
        except Exception as error:
            skipped.append(f"{name}: {error}")
            continue

        destination = ROOT / f"{name} {version}.md"
        stale = [path for path in ROOT.glob(f"{name} *.md") if path != destination]

        if not force and destination.exists() and not stale:
            continue

        source = platform["source"]
        pending.append((platform, version, baseline, destination, stale))
        entry_tasks.update({(version, source), (baseline, source)})
        string_tasks.add((version, source))

    if not pending:
        finish(summary, skipped)
        return

    with ThreadPoolExecutor() as executor:
        for version, source in sorted(entry_tasks):
            executor.submit(load_entries, version, source, cache)
        for version, source in sorted(string_tasks):
            executor.submit(load_strings, version, source, cache)

    for platform, version, baseline, destination, stale in pending:
        name = platform["name"]
        source = platform["source"]
        tokens = platform["tokens"]

        try:
            selected = select(load_entries(version, source, cache), tokens)
            previous = select(load_entries(baseline, source, cache), tokens)
            added = {flag: selected[flag] for flag in sorted(set(selected) - set(previous))}
            document = report(name, version, load_strings(version, source, cache), added)
        except Exception as error:
            skipped.append(f"{name}: {error}")
            continue

        if destination.exists() and not stale:
            if destination.read_text(encoding="utf-8") == document:
                continue

        for path in stale:
            path.unlink()
        destination.write_text(document, encoding="utf-8")
        summary.append(f"{name} {version} +{len(added)}")

    finish(summary, skipped)


if __name__ == "__main__":
    main()
