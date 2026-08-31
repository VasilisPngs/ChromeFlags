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
ROOT = Path(__file__).parent

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
        "tokens": {"kOsIos"},
    },
]

FEATURE_ENTRIES_RE = re.compile(
    r"\bkFeatureEntries\b[^=]*=\s*(?:std::to_array<[^;{]+>\s*\(?)?\{"
)
ENTRY_RE = re.compile(
    r'\{\s*"(?P<name>[A-Za-z0-9][A-Za-z0-9\-\._]*)"\s*,\s*'
    r"(?:[A-Za-z0-9_]+::)*flag_descriptions::\s*(?P<title>k[A-Za-z0-9_]+)\s*,\s*"
    r"(?:[A-Za-z0-9_]+::)*flag_descriptions::\s*(?P<desc>k[A-Za-z0-9_]+)\s*,\s*"
    r"(?P<os>[A-Za-z0-9_ \t\n\|:<>()]+?)\s*,"
)
OS_RE = re.compile(r"kOs[A-Za-z]+")
STRING_RE = re.compile(
    r"(?:inline\s+)?(?:constexpr\s+)?(?:const\s+)?char\s+(k[A-Za-z0-9_]+)\s*\[\]\s*=\s*"
    r'((?:\s*"(?:[^"\\]|\\.)*")+)\s*;',
    re.S,
)
LITERAL_RE = re.compile(r'"((?:[^"\\]|\\.)*)"', re.S)
ESCAPE_RE = re.compile(r"(?:\\x[0-9a-fA-F]{2})+|\\u([0-9a-fA-F]{4})|\\(.)", re.S)
ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\n": ""}


def fetch(url, optional=False):
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
        except OSError:
            if attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            raise


def expand(match):
    run, point, char = match.group(0), match.group(1), match.group(2)
    if char is not None:
        return ESCAPES.get(char, char)
    if point is not None:
        return chr(int(point, 16))
    return bytes.fromhex(run.replace("\\x", "")).decode("utf-8", "replace")


def strip_cpp_comments(text):
    result = []
    i = 0
    n = len(text)
    in_string = False
    in_single_line = False
    in_multi_line = False

    while i < n:
        char = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if in_single_line:
            if char == "\n":
                in_single_line = False
                result.append(char)
            i += 1
        elif in_multi_line:
            if char == "*" and nxt == "/":
                in_multi_line = False
                i += 2
            else:
                i += 1
        elif in_string:
            result.append(char)
            if char == "\\" and i + 1 < n:
                result.append(nxt)
                i += 2
            elif char == '"':
                in_string = False
                i += 1
            else:
                i += 1
        else:
            if char == "/" and nxt == "/":
                in_single_line = True
                i += 2
            elif char == "/" and nxt == "*":
                in_multi_line = True
                i += 2
            elif char == '"':
                in_string = True
                result.append(char)
                i += 1
            else:
                result.append(char)
                i += 1

    return "".join(result)


def feature_entries(text):
    text = strip_cpp_comments(text)
    match = FEATURE_ENTRIES_RE.search(text)
    if not match:
        sys.exit("kFeatureEntries initializer not found")

    start = match.end()
    depth = 1
    index = start

    while index < len(text):
        char = text[index]
        if char == '"':
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == '"':
                    break
                index += 1
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index]
        index += 1

    sys.exit("kFeatureEntries initializer is unterminated")


def parse_entries(text):
    body = feature_entries(text)
    result = {}
    for match in ENTRY_RE.finditer(body):
        result[match.group("name")] = {
            "title_key": match.group("title"),
            "desc_key": match.group("desc"),
            "os": set(OS_RE.findall(match.group("os"))),
        }
    if not result:
        sys.exit("no valid flag entries parsed from kFeatureEntries")
    return result


def parse_strings(text):
    text = strip_cpp_comments(text)
    result = {}
    for match in STRING_RE.finditer(text):
        joined = "".join(LITERAL_RE.findall(match.group(2)))
        result[match.group(1)] = ESCAPE_RE.sub(expand, joined).strip()
    return result


def load(kind, version, source, cache):
    key = (kind, version, source)
    data = cache.get(key)
    if data is None:
        paths = SOURCES[source][kind]
        if kind == "entries":
            data = parse_entries(fetch(f"{RAW}/{version}/{paths}"))
        else:
            data = {}
            for path, optional in paths:
                text = fetch(f"{RAW}/{version}/{path}", optional)
                if text is not None:
                    data.update(parse_strings(text))
        cache[key] = data
    return data


def number(version):
    return tuple(int(part) for part in version.split("."))


def stable(platform):
    history = json.loads(fetch(f"{DASH}?channel=Stable&platform={platform}&num=60"))
    newest = {}
    for item in history:
        found = newest.get(item["milestone"])
        if found is None or number(item["version"]) > number(found):
            newest[item["milestone"]] = item["version"]
    return newest


def select(entries, tokens):
    return {name: entry for name, entry in entries.items() if tokens & entry["os"]}


def escape(text):
    return text.replace("<", "&lt;").replace(">", "&gt;")


def describe(name, entry, strings):
    title = strings.get(entry["title_key"])
    body = strings.get(entry["desc_key"])
    if title is None or body is None:
        sys.exit(f"no title or description for {name}")
    return [
        f"**{escape(title)}**",
        "",
        escape(body),
        "",
        f"`chrome://flags/#{name}`",
        "",
    ]


def report(name, version, strings, selected, added):
    lines = [f"# {name} {version}", ""]
    if not added:
        lines.append("This release added no new flags.")
    for position, flag in enumerate(added):
        if position:
            lines.extend(["---", ""])
        lines.extend(describe(flag, selected[flag], strings))
    return "\n".join(lines).rstrip("\n") + "\n"


def main():
    cache = {}
    title = []

    with ThreadPoolExecutor(max_workers=len(PLATFORMS)) as executor:
        releases_futures = {
            platform["name"]: executor.submit(
                stable, platform.get("dash", platform["name"])
            )
            for platform in PLATFORMS
        }
        releases = {name: future.result() for name, future in releases_futures.items()}

    platform_params = []
    load_tasks = set()

    for platform in PLATFORMS:
        name = platform["name"]
        newest = releases[name]
        if not newest:
            sys.exit(f"no Stable releases listed for {name}")

        milestone = max(newest)
        version = newest[milestone]

        baseline_milestone = milestone - 1
        while baseline_milestone not in newest and baseline_milestone > milestone - 8:
            baseline_milestone -= 1
        if baseline_milestone not in newest:
            sys.exit(f"no earlier Stable release to compare {version} against for {name}")

        baseline = newest[baseline_milestone]
        source = platform["source"]

        platform_params.append((platform, version, baseline))
        load_tasks.add(("entries", version, source))
        load_tasks.add(("entries", baseline, source))
        load_tasks.add(("strings", version, source))

    with ThreadPoolExecutor(max_workers=max(len(load_tasks), 1)) as executor:
        futures = [
            executor.submit(load, kind, version, source, cache)
            for kind, version, source in load_tasks
        ]
        for future in futures:
            future.result()

    for platform, version, baseline in platform_params:
        name = platform["name"]
        source = platform["source"]
        tokens = platform["tokens"]

        selected = select(load("entries", version, source, cache), tokens)
        previous = {
            flag
            for flag, entry in load("entries", baseline, source, cache).items()
            if tokens & entry["os"]
        }
        added = sorted(set(selected) - previous)

        document = report(
            name, version, load("strings", version, source, cache), selected, added
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
    main()
