import contextlib
import http.client
import io
import json
import unittest
import unittest.mock
import urllib.error
import zlib

import chromeflags


def entries(source: str, names: dict[str, str] | None = None) -> dict[str, list[dict]]:
    return chromeflags.parse_entries(chromeflags.strip_cpp_comments(source), names or {})


class TestChromeFlags(unittest.TestCase):
    def test_strip_cpp_comments_preserves_urls(self):
        source = 'constexpr char kUrl[] = "https://example.com/path?foo=bar//not_comment"; // Actual comment\nint value = 1;'
        stripped = chromeflags.strip_cpp_comments(source)
        self.assertIn("https://example.com/path?foo=bar//not_comment", stripped)
        self.assertNotIn("Actual comment", stripped)
        self.assertIn("int value = 1;", stripped)

    def test_strip_cpp_comments_preserves_strings_and_newlines(self):
        source = '/* Block Comment */\nconstexpr char kTest[] = "value /* not a comment */"; /* Multi\nline */\nint x = 1;'
        stripped = chromeflags.strip_cpp_comments(source)
        self.assertIn('constexpr char kTest[] = "value /* not a comment */";', stripped)
        self.assertIn("int x = 1;", stripped)
        self.assertNotIn("Block Comment", stripped)
        self.assertNotIn("Multi", stripped)

    def test_feature_entries_parses_std_to_array_initializer(self):
        source = """
        constexpr auto kFeatureEntries = std::to_array<flags_ui::FeatureEntry>({
            {"alpha",
             flag_descriptions::kAlphaTitle,
             flag_descriptions::kAlphaDescription,
             kOsDesktop | kOsAll,
             FEATURE_VALUE_TYPE(kAlpha)},
        });
        """
        self.assertEqual(
            entries(source)["alpha"],
            [{"title_key": "kAlphaTitle", "desc_key": "kAlphaDescription", "os": {"kOsDesktop", "kOsAll"}}],
        )

    def test_parse_entries_handles_nested_commas(self):
        source = """
        constexpr auto kFeatureEntries = {
            {"alpha",
             contextual_tasks::flag_descriptions::kAlphaTitle,
             contextual_tasks::flag_descriptions::kAlphaDescription,
             kOsDesktop | kOsLinux,
             FEATURE_VALUE_TYPE(SomeFeature, Foo(1, 2))},
            {"beta",
             flag_descriptions::kBetaTitle,
             flag_descriptions::kBetaDescription,
             kOsAndroid,
             nullptr},
        };
        """
        parsed = entries(source)
        self.assertEqual(set(parsed), {"alpha", "beta"})
        self.assertEqual(parsed["beta"][0]["os"], {"kOsAndroid"})

    def test_parse_entries_resolves_identifier_flag_names(self):
        source = """
        const char kGammaInternalName[] = "gamma";
        constexpr auto kFeatureEntries = {
            {kGammaInternalName,
             flag_descriptions::kGammaTitle,
             flag_descriptions::kGammaDescription,
             kOsWin,
             nullptr},
            {switches::kDelta,
             flag_descriptions::kDeltaTitle,
             flag_descriptions::kDeltaDescription,
             kOsAll,
             nullptr},
        };
        """
        parsed = entries(source, {"kDelta": "delta"})
        self.assertEqual(set(parsed), {"gamma", "delta"})
        self.assertEqual(parsed["gamma"][0]["os"], {"kOsWin"})
        self.assertEqual(parsed["delta"][0]["title_key"], "kDeltaTitle")

    def test_parse_entries_rejects_unresolvable_identifier(self):
        source = """
        constexpr auto kFeatureEntries = {
            {switches::kUnknownFlag,
             flag_descriptions::kAlphaTitle,
             flag_descriptions::kAlphaDescription,
             kOsAll,
             nullptr},
        };
        """
        with self.assertRaises(ValueError):
            entries(source)

    def test_parse_entries_rejects_entry_without_os_token(self):
        source = """
        constexpr auto kFeatureEntries = {
            {"alpha",
             flag_descriptions::kAlphaTitle,
             flag_descriptions::kAlphaDescription,
             0,
             nullptr},
        };
        """
        with self.assertRaises(ValueError):
            entries(source)

    def test_parse_entries_rejects_an_unknown_platform_token(self):
        source = """
        constexpr auto kFeatureEntries = {
            {"alpha", flag_descriptions::kAlphaTitle,
             flag_descriptions::kAlphaDescription, kOsAndroidDesktop, nullptr},
        };
        """
        with self.assertRaises(ValueError):
            entries(source)

    def test_parse_entries_keeps_every_entry_of_a_flag(self):
        source = """
        constexpr auto kFeatureEntries = {
            {"alpha",
             flag_descriptions::kAlphaTitle,
             flag_descriptions::kAlphaDescription,
             kOsWin,
             nullptr},
            {"alpha",
             flag_descriptions::kAlphaTitle,
             flag_descriptions::kAlphaDescription,
             kOsAndroid,
             nullptr},
        };
        """
        self.assertEqual([variant["os"] for variant in entries(source)["alpha"]], [{"kOsWin"}, {"kOsAndroid"}])

    def test_parse_entries_detects_incomplete_parsing(self):
        source = """
        constexpr auto kFeatureEntries = {
            {"broken_flag"},
        };
        """
        with self.assertRaises(ValueError):
            entries(source)

    def test_parse_entries_keeps_one_branch_when_each_branch_closes_the_entry(self):
        source = """
        constexpr auto kFeatureEntries = {
            {"alpha", flag_descriptions::kAlphaTitle,
             flag_descriptions::kAlphaDescription, kOsAndroid,
        #if BUILDFLAG(IS_DESKTOP_ANDROID)
             FEATURE_VALUE_TYPE(kAlphaDesktop)},
        #else
             FEATURE_VALUE_TYPE(kAlpha)},
        #endif
            {"beta", flag_descriptions::kBetaTitle,
             flag_descriptions::kBetaDescription, kOsWin, nullptr},
        };
        """
        parsed = entries(source)
        self.assertEqual(set(parsed), {"alpha", "beta"})
        self.assertEqual([variant["os"] for variant in parsed["alpha"]], [{"kOsAndroid"}])
        self.assertEqual(parsed["beta"][0]["os"], {"kOsWin"})

    def test_parse_entries_keeps_alternative_entries_from_every_branch(self):
        source = """
        constexpr auto kFeatureEntries = {
        #if BUILDFLAG(IS_CHROMEOS)
            {"gamma", flag_descriptions::kGammaTitle,
             flag_descriptions::kGammaDescription, kOsCrOS, nullptr},
        #elif BUILDFLAG(IS_WIN) || \\
            BUILDFLAG(IS_MAC)
            {"gamma", flag_descriptions::kGammaTitle,
             flag_descriptions::kGammaDescription, kOsWin | kOsMac, nullptr},
        #endif
        };
        """
        self.assertEqual([variant["os"] for variant in entries(source)["gamma"]], [{"kOsCrOS"}, {"kOsWin", "kOsMac"}])

    def test_feature_entries_rejects_an_initializer_that_closes_early(self):
        source = """
        constexpr auto kFeatureEntries = {
            {"alpha", flag_descriptions::kAlphaTitle,
             flag_descriptions::kAlphaDescription, kOsAll, nullptr}},
            {"beta", flag_descriptions::kBetaTitle,
             flag_descriptions::kBetaDescription, kOsAll, nullptr},
        };
        """
        with self.assertRaises(ValueError):
            entries(source)

    def test_parse_entries_accepts_literal_titles_and_descriptions(self):
        source = """
        constexpr auto kFeatureEntries = {
            {"alpha", "Alpha title", "Alpha " "description", kOsAll, nullptr},
        };
        """
        entry = entries(source)["alpha"][0]
        self.assertEqual(chromeflags.describe("alpha", entry, {}, []), ("Alpha title", "Alpha description"))

    def test_feature_entries_rejects_an_unknown_include(self):
        source = """
        constexpr auto kFeatureEntries = {
        #include "chrome/browser/other_flags_gen.inc"
            {"alpha", flag_descriptions::kAlphaTitle,
             flag_descriptions::kAlphaDescription, kOsAll, nullptr},
        };
        """
        with self.assertRaises(ValueError):
            entries(source)

    def test_expand_unexpire_adds_the_flags_of_the_two_previous_milestones(self):
        generator = chromeflags.UNEXPIRE_FRAGMENT + "\n".join(chromeflags.UNEXPIRE_LOGIC)
        source = chromeflags.strip_cpp_comments("""
        constexpr auto kFeatureEntries = {
        #include "build/chromeos_buildflags.h"
        #include "chrome/browser/unexpire_flags_gen.inc"
            {"alpha", flag_descriptions::kAlphaTitle,
             flag_descriptions::kAlphaDescription, kOsWin, nullptr},
        };
        """)
        with unittest.mock.patch.object(chromeflags, "fetch_chromium", return_value=generator):
            parsed = chromeflags.parse_entries(chromeflags.expand_unexpire(source, "156.0.8078.49"), {})
        self.assertEqual(set(parsed), {"alpha", "temporary-unexpire-flags-m154", "temporary-unexpire-flags-m155"})
        entry = parsed["temporary-unexpire-flags-m155"][0]
        self.assertEqual(entry["os"], {"kOsAll"})
        self.assertEqual(
            chromeflags.describe("temporary-unexpire-flags-m155", entry, {}, []),
            (
                "Temporarily unexpire M155 flags.",
                "Temporarily unexpire flags that expired as of M155. These flags will be removed soon.",
            ),
        )

    def test_expand_unexpire_rejects_a_changed_generator(self):
        with unittest.mock.patch.object(chromeflags, "fetch_chromium", return_value="return [mstone]"):
            with self.assertRaises(ValueError):
                chromeflags.expand_unexpire(chromeflags.UNEXPIRE_INCLUDE, "156.0.8078.49")

    def test_select_includes_kos_all(self):
        table = {
            "shared": [{"os": {"kOsAll"}}],
            "desktop": [{"os": {"kOsDesktop"}}],
            "android": [{"os": {"kOsAndroid"}}],
        }
        selected = chromeflags.select(table, {"kOsWin", "kOsAll", "kOsDesktop"})
        self.assertEqual(set(selected), {"shared", "desktop"})

    def test_select_takes_the_entry_of_each_platform(self):
        source = """
        constexpr auto kFeatureEntries = {
        #if BUILDFLAG(IS_WIN)
            {"use-angle", flag_descriptions::kUseAngleName,
             flag_descriptions::kUseAngleDescriptionWindows, kOsWin, nullptr},
        #elif BUILDFLAG(IS_ANDROID)
            {"use-angle", flag_descriptions::kUseAngleName,
             flag_descriptions::kUseAngleDescriptionAndroid, kOsAndroid, nullptr},
        #endif
        };
        """
        parsed = entries(source)
        windows = chromeflags.select(parsed, {"kOsWin", "kOsAll"})
        android = chromeflags.select(parsed, {"kOsAndroid", "kOsAll"})
        self.assertEqual(windows["use-angle"]["desc_key"], "kUseAngleDescriptionWindows")
        self.assertEqual(android["use-angle"]["desc_key"], "kUseAngleDescriptionAndroid")

    def test_parse_strings_supports_concatenated_literals_and_escapes(self):
        source = r'''
        constexpr char kTitle[] = "First " "Second";
        const char kDescription[] = "Line one\nLine two";
        inline constexpr char kUnicode[] = "A\u00E9";
        constexpr char kUtf8[] = "A\xC3\xA9";
        '''
        strings = chromeflags.parse_strings(source)
        self.assertEqual(strings["kTitle"], "First Second")
        self.assertEqual(strings["kDescription"], "Line one\nLine two")
        self.assertEqual(strings["kUnicode"], "Aé")
        self.assertEqual(strings["kUtf8"], "Aé")

    def test_decode_cpp_string_supports_surrogate_pairs(self):
        self.assertEqual(chromeflags.decode_cpp_string(r"\uD83D\uDE00"), "😀")

    def test_decode_cpp_string_replaces_unpaired_surrogates(self):
        self.assertEqual(chromeflags.decode_cpp_string(r"\uD83D"), "\ufffd")
        self.assertEqual(chromeflags.decode_cpp_string(r"\uDE00"), "\ufffd")

    def test_escape_encodes_html_metacharacters(self):
        self.assertEqual(chromeflags.escape("a & b <tag>\nnext"), "a &amp; b &lt;tag&gt; next")

    def test_describe_fallback_for_missing_keys(self):
        entry = {"title_key": "kMissingTitle", "desc_key": "kMissingDesc", "os": {"kOsAll"}}
        problems = []
        self.assertEqual(chromeflags.describe("test-flag", entry, {}, problems), ("kMissingTitle", "kMissingDesc"))
        self.assertEqual(problems, [
            "missing title string kMissingTitle for test-flag",
            "missing description string kMissingDesc for test-flag",
        ])

    def test_finish_fails_only_for_lasting_problems(self):
        busy = urllib.error.HTTPError("https://example.test", 503, "busy", {}, None)
        missing = urllib.error.HTTPError("https://example.test", 404, "missing", {}, None)
        self.addCleanup(busy.close)
        self.addCleanup(missing.close)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(chromeflags.finish([], {"Windows": busy, "Linux": urllib.error.URLError("down")}, []), 0)
            self.assertEqual(chromeflags.finish([], {"Windows": missing}, []), 1)
            self.assertEqual(chromeflags.finish([], {"Windows": ValueError("moved")}, []), 1)
            self.assertEqual(chromeflags.finish([], {}, ["missing title string kTitle for alpha"]), 1)
            with self.assertRaises(RuntimeError):
                chromeflags.finish([], {platform["name"]: busy for platform in chromeflags.PLATFORMS}, [])

    def test_current_milestone_stops_at_the_settled_phase(self):
        releases = {
            153: ("153.0.8010.55", 3_000),
            154: ("154.0.8037.58", 2_000),
            155: ("155.0.8059.12", 3_000),
        }
        self.assertEqual(chromeflags.current_milestone(releases, 154), 154)

    def test_current_milestone_passes_the_cap_once_a_platform_moves_on(self):
        releases = {
            152: ("152.0.7977.64", 1_000),
            153: ("153.0.8010.24", 2_000),
            154: ("154.0.8037.41", 5_000),
        }
        self.assertEqual(chromeflags.current_milestone(releases, 153), 154)

    def test_current_milestone_holds_back_while_an_older_one_is_patched(self):
        releases = {
            152: ("152.0.7977.85", 1_000),
            153: ("153.0.8010.55", 3_000),
            155: ("155.0.8059.12", 3_000),
        }
        self.assertEqual(chromeflags.current_milestone(releases, None), 153)

    def test_current_milestone_without_a_cap_takes_a_settled_milestone(self):
        releases = {
            153: ("153.0.8010.24", 2_000),
            154: ("154.0.8037.41", 5_000),
        }
        self.assertEqual(chromeflags.current_milestone(releases, None), 154)

    def test_current_milestone_accepts_a_single_milestone(self):
        self.assertEqual(chromeflags.current_milestone({153: ("153.0.8010.47", 9)}, 154), 153)

    def test_current_milestone_ignores_older_extended_support(self):
        releases = {
            150: ("150.0.7871.200", 9_000),
            154: ("154.0.8037.58", 3_000),
        }
        self.assertEqual(chromeflags.current_milestone(releases, 154), 154)

    def test_stable_keeps_releases_that_carry_no_timestamp(self):
        payload = json.dumps([
            {"version": "154.0.8037.58"},
            {"version": "153.0.8010.55", "time": "not a number"},
        ])
        with unittest.mock.patch.object(chromeflags, "fetch", return_value=payload):
            releases = chromeflags.stable("Windows")
        self.assertEqual(releases, {154: ("154.0.8037.58", 0), 153: ("153.0.8010.55", 0)})

    def test_current_milestone_falls_back_to_the_newest_without_any_signal(self):
        releases = {153: ("153.0.8010.55", 0), 154: ("154.0.8037.58", 0)}
        self.assertEqual(chromeflags.current_milestone(releases, None), 154)

    def test_fetch_retries_transient_transport_errors(self):
        class Response:
            headers = {}

            def read(self):
                return b"ok"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        for error in (
            http.client.IncompleteRead(b"partial", 100),
            http.client.BadStatusLine("garbage"),
            zlib.error("corrupt"),
            EOFError("truncated"),
            urllib.error.URLError("down"),
        ):
            with self.subTest(error=type(error).__name__):
                outcomes = [error, Response()]
                calls = []

                def opener(request, timeout):
                    calls.append(request)
                    outcome = outcomes.pop(0)
                    if isinstance(outcome, BaseException):
                        raise outcome
                    return outcome

                with unittest.mock.patch.object(chromeflags.urllib.request, "urlopen", opener), \
                        unittest.mock.patch.object(chromeflags.time, "sleep"):
                    self.assertEqual(chromeflags.fetch("https://example.test"), "ok")
                self.assertEqual(len(calls), 2)

    def test_fetch_does_not_retry_a_missing_resource(self):
        error = urllib.error.HTTPError("https://example.test", 404, "missing", {}, None)
        with unittest.mock.patch.object(chromeflags.urllib.request, "urlopen", side_effect=error) as opener, \
                unittest.mock.patch.object(chromeflags.time, "sleep"):
            with self.assertRaises(urllib.error.HTTPError):
                chromeflags.fetch("https://example.test")
        self.assertEqual(opener.call_count, 1)

    def test_number_validates_chrome_versions(self):
        self.assertEqual(chromeflags.number("153.0.8010.12"), (153, 0, 8010, 12))
        with self.assertRaises(ValueError):
            chromeflags.number("153.8010")

    def test_parse_entries_rejects_unparseable_input(self):
        with self.assertRaises(ValueError):
            entries("constexpr auto something_else = {}; ")


if __name__ == "__main__":
    unittest.main()
