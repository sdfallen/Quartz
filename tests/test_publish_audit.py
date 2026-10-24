import unittest
from scripts.audit_publish import content_rules, forbidden_path


class PublishAuditTests(unittest.TestCase):
    def test_private_runtime_and_rotated_logs_denied(self):
        for path in ('.env', '.env.production', 'assistant.log.1', 'quartz_projects.json',
                     'labs/run/output.json', '.squad/messages.db', 'dist/Quartz.exe', 'keys/key.pem'):
            with self.subTest(path=path): self.assertTrue(forbidden_path(path))

    def test_source_sample_and_approved_assets_allowed(self):
        for path in ('.env.example', 'core/desktop_broker.py', 'requirements.txt',
                     'assets/branding/quartz-q.png', '.github/workflows/tests.yml'):
            with self.subTest(path=path): self.assertFalse(forbidden_path(path))

    def test_provider_token_is_identified_without_returning_value(self):
        value = b'ghp_' + b'a' * 36
        self.assertEqual(content_rules(value), ['github-token'])

    def test_local_env_value_match_is_not_printed(self):
        value = b'local-secret-' + b'z' * 12
        self.assertEqual(content_rules(b'config=' + value, [value]), ['local-env-secret-match'])

    def test_env_placeholder_and_variable_read_are_safe(self):
        self.assertEqual(content_rules(b'NVIDIA_API_KEY=\nkey=os.getenv("GITHUB_TOKEN", "")'), [])


if __name__ == '__main__': unittest.main()
