import unittest
import chromeflags


class TestChromeFlags(unittest.TestCase):
    def test_strip_cpp_comments_preserves_urls(self):
        source = 'constexpr char kUrl[] = "https://example.com/path?foo=bar//not_comment"; // Actual comment'
        stripped = chromeflags.strip_cpp_comments(source)
        self.assertIn("https://example.com/path?foo=bar//not_comment", stripped)
        self.assertNotIn("Actual comment", stripped)

    def test_strip_cpp_comments_block_comments(self):
        source = '/* Block Comment */ constexpr char kTest[] = "value"; /* Multi\nline */'
        stripped = chromeflags.strip_cpp_comments(source)
        self.assertNotIn("Block Comment", stripped)
        self.assertNotIn("Multi", stripped)
        self.assertIn('constexpr char kTest[] = "value";', stripped.strip())

    def test_parse_entries_standard_and_namespaced(self):
        source = """
        constexpr auto kFeatureEntries = std::to_array<flags_ui::FeatureEntry>({
            {"contextual-tasks",
             contextual_tasks::flag_descriptions::kContextualTasksName,
             contextual_tasks::flag_descriptions::kContextualTasksDescription,
             kOsDesktop | kOsAndroid,
             FEATURE_VALUE_TYPE(kContextualTasks)},
        });
        """
        entries = chromeflags.parse_entries(source)
        self.assertIn("contextual-tasks", entries)
        self.assertEqual(
            entries["contextual-tasks"]["title_key"], "kContextualTasksName"
        )
        self.assertEqual(
            entries["contextual-tasks"]["desc_key"], "kContextualTasksDescription"
        )


if __name__ == "__main__":
    unittest.main()
