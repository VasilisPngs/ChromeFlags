import gzip
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PLATFORMS = [
    {
        "name": "Android",
        "source": "chrome/browser/about_flags.cc",
        "tokens": {"kOsAndroid"},
    },
    {
        "name": "Linux",
        "source": "chrome/browser/about_flags.cc",
        "tokens": {"kOsDesktop", "kOsLinux"},
    },
    {
        "name": "Windows",
        "source": "chrome/browser/about_flags.cc",
        "tokens": {"kOsDesktop", "kOsWin"},
    },
    {
        "name": "macOS",
        "source": "chrome/browser/about_flags.cc",
        "tokens": {"kOsDesktop", "kOsMac"},
    },
    {
        "name": "iOS-iPadOS",
        "source": "ios/chrome/browser/flags/about_flags.mm",
        "tokens": {"kOsIos"},
    },
]

FEATURE_ENTRIES_RE = re.compile(
    r"\bkFeatureEntries\b\s*(?:\[\]\s*)?=\s*\{", re.MULTILINE
)


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


def expand(macro: str, source: str) -> list[str]:
    pattern = rf"#define\s+{re.escape(macro)}\s*\((.*?)\)"
    match = re.search(pattern, source)
    if not match:
        return []
    params = [param.strip() for param in match.group(1).split(",")]
    pattern = rf"\b{re.escape(macro)}\s*\((.*?)\)"
    matches = re.findall(pattern, source, re.DOTALL)
    expanded = []
    for m in matches:
        args = [arg.strip() for arg in m.split(",")]
        if len(args) == len(params):
            expanded.append(dict(zip(params, args)))
    return expanded


def strip_cpp_comments(text: str) -> str:
    pattern = r'//.*?$|/\*.*?\*/|"(?:\\.|[^\\"])*"'
    def replacer(match: re.Match) -> str:
        s = match.group(0)
        return s if s.startswith('"') else ('\n' if s.startswith('//') else '')
    return re.sub(pattern, replacer, text, flags=re.MULTILINE | re.DOTALL)


def feature_entries(text: str) -> str:
    clean_text = strip_cpp_comments(text)
    match = FEATURE_ENTRIES_RE.search(clean_text)
    if not match:
        sys.exit("kFeatureEntries initializer not found")

    start = match.end()
    depth = 1
    index = start

    while index < len(clean_text):
        char = clean_text[index]
        if char == '"':
            index += 1
            while index < len(clean_text):
                if clean_text[index] == "\\":
                    index += 2
                    continue
                if clean_text[index] == '"':
                    break
                index += 1
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return clean_text[start:index]
        index += 1

    sys.exit("kFeatureEntries initializer is unterminated")


def parse_entries(source: str) -> dict[str, dict]:
    block = feature_entries(source)
    entries = {}
    pattern = r'\{\s*"([^"]+)"\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^\}]+)\}'

    for match in re.finditer(pattern, block):
        flag, title, description, os_flags = match.groups()
        os_set = {
            token.strip()
            for token in os_flags.replace("|", " ").split()
            if token.strip()
        }
        entries[flag] = {
            "title": title.strip(),
            "description": description.strip(),
            "os": os_set,
        }

    return entries


def parse_strings(source: str) -> dict[str, str]:
    strings = {}
    pattern = r'(?:constexpr\s+char\s+|const\n?char\s+)(\w+)\[\]\s*=\s*"((?:[^"\\]|\\.)*)";'

    for name, value in re.findall(pattern, source):
        try:
            decoded = value.encode("utf-8").decode("unicode_escape")
        except Exception:
            decoded = value
        strings[name] = decoded

    return strings


def load(kind: str, version: str, source: str, cache: dict) -> dict:
    key = (kind, version, source)
    if key in cache:
        return cache[key]

    if kind == "entries":
        url = f"https://chromium.googlesource.com/chromium/src/+/{version}/{source}?format=TEXT"
        content = fetch(url)
        import base64
        decoded = base64.b64decode(content).decode("utf-8", "replace")
        result = parse_entries(decoded)
    elif kind == "strings":
        url = f"https://chromium.googlesource.com/chromium/str/+/{version}/chrome/app/generated_resources.grd?format=TEXT"
        content = fetch(url, optional=True)
        if content:
            import base64
            decoded = base64.b64decode(content).decode("utf-8", "replace")
            result = parse_strings(decoded)
        else:
            result = {}
    else:
        raise ValueError(f"Unknown kind: {kind}")

    cache[key] = result
    return result


def number(version_str: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version_str.split("."))


def stable(platform_name: str) -> dict[int, str]:
    url = f"https://chromiumdash.appspot.com/fetch_releases?platform={platform_name}&channel=Stable&num=100"
    content = fetch(url)
    import json
    data = json.loads(content)

    releases = {}
    for item in data:
        version = item.get("version")
        if not version:
            continue
        milestone = int(version.split(".")[0])
        if milestone not in releases or number(version) > number(releases[milestone]):
            releases[milestone] = version

    return releases


def select(entries: dict[str, dict], tokens: set[str]) -> dict[str, dict]:
    return {
        flag: entry
        for flag, entry in entries.items()
        if tokens & entry["os"]
    }


def escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def describe(flag: str, entry: dict, strings: dict) -> tuple[str, str]:
    title_key = entry["title"]
    desc_key = entry["description"]

    title = strings.get(title_key) or flag
    desc = strings.get(desc_key) or "No description available."

    return title, desc


def report(
    platform: str,
    version: str,
    strings: dict,
    selected: dict[str, dict],
    added: list[str],
) -> str:
    lines = [
        f"# {platform} {version}",
        "",
        f"Total flags: **{len(selected)}** | New flags: **{len(added)}**",
        "",
    ]

    if added:
        lines.extend([
            "## New Flags",
            "",
            "| Flag | Title | Description |",
            "| :--- | :--- | :--- |",
        ])
        for flag in added:
            title, desc = describe(flag, selected[flag], strings)
            lines.append(f"| `{flag}` | {escape(title)} | {escape(desc)} |")
        lines.append("")

    lines.extend([
        "## All Flags",
        "",
        "| Flag | Title | Description |",
        "| :--- | :--- | :--- |",
    ])

    for flag in sorted(selected.keys()):
        title, desc = describe(flag, selected[flag], strings)
        lines.append(f"| `{flag}` | {escape(title)} | {escape(desc)} |")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    cache = {}
    title = []

    with ThreadPoolExecutor(max_workers=16) as executor:
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
