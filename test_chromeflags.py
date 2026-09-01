import unittest

import chromeflags


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
        entries = chromeflags.parse_entries(source)
        self.assertEqual(entries["alpha"]["title_key"], "kAlphaTitle")
        self.assertEqual(entries["alpha"]["desc_key"], "kAlphaDescription")
        self.assertEqual(entries["alpha"]["os"], {"kOsDesktop", "kOsAll"})

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
        entries = chromeflags.parse_entries(source)
        self.assertEqual(set(entries), {"alpha", "beta"})
        self.assertEqual(entries["beta"]["os"], {"kOsAndroid"})

    def test_select_includes_kos_all(self):
        entries = {
            "shared": {"os": {"kOsAll"}},
            "desktop": {"os": {"kOsDesktop"}},
            "android": {"os": {"kOsAndroid"}},
        }
        selected = chromeflags.select(entries, {"kOsWindows", "kOsAll", "kOsDesktop"})
        self.assertEqual(set(selected), {"shared", "desktop"})

    def test_parse_strings_supports_concatenated_literals_and_escapes(self):
        source = r'''
        constexpr char kTitle[] = "First " "Second";
        const char kDescription[] = "Line one\nLine two";
        inline constexpr char kUnicode[] = "A\u00E9";
        '''
        strings = chromeflags.parse_strings(source)
        self.assertEqual(strings["kTitle"], "First Second")
        self.assertEqual(strings["kDescription"], "Line one\nLine two")
        self.assertEqual(strings["kUnicode"], "Aé")

    def test_parse_entries_rejects_unparseable_input(self):
        with self.assertRaises(ValueError):
            chromeflags.parse_entries("constexpr auto something_else = {}; ")


if __name__ == "__main__":
    unittest.main()
