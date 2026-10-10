"""Isolated setup and release checks; no downloads, prompts, or personal data."""
import contextlib
import io
import json
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch

import build_release
import install


class InstallTests(unittest.TestCase):
    def test_version_comparison(self):
        self.assertLess(install.version_tuple("0.34.9"), (0, 35, 0))
        self.assertEqual(install.version_tuple("0.35"), (0, 35, 0))
        self.assertGreater(install.version_tuple("0.40.2"), (0, 35, 0))
        with self.assertRaises(ValueError):
            install.version_tuple("unknown")

    def test_old_ollama_is_rejected(self):
        with patch('install.get_json', return_value={'version': '0.34.9'}):
            with self.assertRaises(RuntimeError):
                install.check_ollama(True)

    def test_offline_fix_hint(self):
        with patch('install.get_json', side_effect=urllib.error.URLError('offline')):
            with self.assertRaisesRegex(RuntimeError, 'ollama serve'):
                install.check_ollama(True)

    def test_missing_models_are_not_downloaded_without_choice(self):
        output = io.StringIO()
        with patch('install.get_json', side_effect=[{'version': '0.40.2'}, {'models': []}]), patch('install.configured_models', return_value=['local:model']), patch('install.subprocess.run') as download, contextlib.redirect_stdout(output):
            install.check_ollama(True)
        download.assert_not_called()
        self.assertIn('ollama pull local:model', output.getvalue())

    def test_model_download_requires_yes_and_uses_argument_list(self):
        with patch('install.get_json', side_effect=[{'version': '0.40.2'}, {'models': []}]), patch('install.configured_models', return_value=['local:model']), patch('builtins.input', return_value='y'), patch('install.subprocess.run') as download, contextlib.redirect_stdout(io.StringIO()):
            install.check_ollama()
        download.assert_called_once_with(['ollama', 'pull', 'local:model'], check=True)

    def test_remote_alias_is_rejected(self):
        with patch('install.get_json', side_effect=[{'version': '0.40.2'}, {'models': [{'name': 'innocent:model', 'remote_host': 'https://example.com'}]}]), patch('install.configured_models', return_value=['innocent:model']), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'remote'):
                install.check_ollama(True)

    def test_setup_reuses_environment_and_generates_launcher(self):
        with tempfile.TemporaryDirectory(prefix='orb install ') as directory:
            root = Path(directory)
            python = root / '.venv' / 'Scripts' / 'python.exe'
            python.parent.mkdir(parents=True)
            python.write_bytes(b'fixture')
            with patch('install.ROOT', root), patch('install.subprocess.run') as install_deps, patch('install.check_ollama') as check, patch('install.venv.EnvBuilder') as create, contextlib.redirect_stdout(io.StringIO()):
                install.main(['--non-interactive'])
            create.assert_not_called()
            check.assert_called_once_with(True)
            self.assertEqual(install_deps.call_args.args[0][:4], [str(python), '-m', 'pip', 'install'])
            self.assertEqual((root / 'start.bat').read_text(encoding='ascii'), install.START_BAT)

    def test_setup_creates_new_environment_without_touching_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            marker = root / 'data' / 'keep.txt'
            marker.write_text('preserve')
            with patch('install.ROOT', root), patch('install.subprocess.run'), patch('install.check_ollama'), patch('install.venv.EnvBuilder') as create, contextlib.redirect_stdout(io.StringIO()):
                install.main([])
            create.assert_called_once_with(with_pip=True)
            create.return_value.create.assert_called_once_with(root / '.venv')
            self.assertEqual(marker.read_text(), 'preserve')

    def test_shipped_launcher_matches_installer_template(self):
        self.assertEqual((install.ROOT / 'start.bat').read_text(encoding='ascii'), install.START_BAT)


class ReleaseTests(unittest.TestCase):
    def test_audit_flags_secrets_without_echoing_values(self):
        token = 'ghp_' + 'a' * 36
        findings = build_release.audit({'example.txt': ('token: ' + token).encode()})
        self.assertEqual(findings[0]['kind'], 'GitHub token')
        self.assertNotIn(token, json.dumps(findings))

    def test_audit_flags_personal_paths(self):
        private_path = 'C:' + chr(92) + 'Users' + chr(92) + 'Example' + chr(92) + 'private'
        self.assertEqual(build_release.audit({'example.txt': private_path.encode()})[0]['kind'], 'personal Windows path')

    def test_archive_contains_only_allowed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in build_release.FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('safe fixture', encoding='utf-8')
            for name in ('data/orb.db', '.env', '.venv/private.txt', 'test-artifacts/private.txt'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('not for distribution')
            archive, report = build_release.build(root)
            with zipfile.ZipFile(archive) as zipped:
                self.assertEqual(set(zipped.namelist()), {build_release.PACKAGE + '/' + name for name in build_release.FILES})
            self.assertEqual(report['credential_findings'], [])


if __name__ == '__main__':
    unittest.main()
