import unittest

import chromeflags


def entries(source: str, names: dict[str, str] | None = None) -> dict[str, dict]:
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

    def test_feature_entries_supports_comments_before_initializer(self):
        source = """
        // This used to break comment-aware extraction in earlier versions.
        constexpr auto kFeatureEntries = std::to_array<flags_ui::FeatureEntry>({
            {"alpha",
             flag_descriptions::kAlphaTitle,
             flag_descriptions::kAlphaDescription,
             kOsDesktop | kOsAll,
             FEATURE_VALUE_TYPE(kAlpha)},
        });
        """
        parsed = entries(source)
        self.assertEqual(parsed["alpha"]["title_key"], "kAlphaTitle")
        self.assertEqual(parsed["alpha"]["desc_key"], "kAlphaDescription")
        self.assertEqual(parsed["alpha"]["os"], {"kOsDesktop", "kOsAll"})

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
        self.assertEqual(parsed["beta"]["os"], {"kOsAndroid"})

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
        self.assertEqual(parsed["gamma"]["os"], {"kOsWin"})
        self.assertEqual(parsed["delta"]["title_key"], "kDeltaTitle")

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

    def test_parse_entries_merges_duplicate_flag_names(self):
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
        parsed = entries(source)
        self.assertEqual(parsed["alpha"]["os"], {"kOsWin", "kOsAndroid"})

    def test_parse_entries_detects_incomplete_parsing(self):
        source = """
        constexpr auto kFeatureEntries = {
            {"broken_flag"},
        };
        """
        with self.assertRaises(ValueError):
            entries(source)

    def test_select_includes_kos_all(self):
        table = {
            "shared": {"os": {"kOsAll"}},
            "desktop": {"os": {"kOsDesktop"}},
            "android": {"os": {"kOsAndroid"}},
        }
        selected = chromeflags.select(table, {"kOsWin", "kOsAll", "kOsDesktop"})
        self.assertEqual(set(selected), {"shared", "desktop"})

    def test_parse_strings_supports_concatenated_literals_and_escapes(self):
        source = r'''
        constexpr char kTitle[] = "First " "Second";
        const char kDescription[] = "Line one\nLine two";
        inline constexpr char kUnicode[] = "Aé";
        constexpr char kUtf8[] = "A\xC3\xA9";
        '''
        strings = chromeflags.parse_strings(source)
        self.assertEqual(strings["kTitle"], "First Second")
        self.assertEqual(strings["kDescription"], "Line one\nLine two")
        self.assertEqual(strings["kUnicode"], "Aé")
        self.assertEqual(strings["kUtf8"], "Aé")

    def test_decode_cpp_string_supports_surrogate_pairs(self):
        self.assertEqual(chromeflags.decode_cpp_string(r"😀"), "😀")

    def test_decode_cpp_string_replaces_unpaired_surrogates(self):
        self.assertEqual(chromeflags.decode_cpp_string(r"\uD83D"), "�")
        self.assertEqual(chromeflags.decode_cpp_string(r"\uDE00"), "�")

    def test_escape_encodes_html_metacharacters(self):
        self.assertEqual(chromeflags.escape("a & b <tag>\nnext"), "a &amp; b &lt;tag&gt; next")

    def test_describe_fallback_for_missing_keys(self):
        entry = {"title_key": "kMissingTitle", "desc_key": "kMissingDesc", "os": {"kOsAll"}}
        title, desc = chromeflags.describe("test-flag", entry, {})
        self.assertEqual(title, "kMissingTitle")
        self.assertEqual(desc, "kMissingDesc")

    def test_number_validates_chrome_versions(self):
        self.assertEqual(chromeflags.number("153.0.8010.12"), (153, 0, 8010, 12))
        with self.assertRaises(ValueError):
            chromeflags.number("153.8010")

    def test_parse_entries_rejects_unparseable_input(self):
        with self.assertRaises(ValueError):
            entries("constexpr auto something_else = {}; ")


if __name__ == "__main__":
    unittest.main()
