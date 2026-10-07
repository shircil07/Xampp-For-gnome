import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "lib" / "xampp-download.sh"
PAYLOAD = b"#!/bin/sh\necho fake installer\n"
GOOD = hashlib.sha256(PAYLOAD).hexdigest()
PINNED = "xampp-linux-x64-8.2.12-0-installer.run"

# A curl stand-in that behaves like a resumed download: it logs its argv, continues $FAKE_PAYLOAD
# from the --output file's current size, and while the counter file is positive it delivers only
# one more byte and fails. A retry that starts over while keeping the .part ends up with extra
# bytes; the flag assertions check that --continue-at is actually passed.
FAKE_CURL = """#!/bin/bash
printf '%s\\n' "$*" >> "$FAKE_LOG"
out=""
while (($#)); do [[ $1 == --output ]] && out=$2; shift; done
size=$(stat -c %s "$out" 2>/dev/null || echo 0)
rest=${FAKE_PAYLOAD:size}
fails=$(cat "$FAKE_FAILS_FILE" 2>/dev/null || echo 0)
if ((fails > 0)); then
  echo $((fails - 1)) > "$FAKE_FAILS_FILE"
  printf '%s' "${rest:0:1}" >> "$out"
  exit 18
fi
printf '%s' "$rest" >> "$out"
"""


class LibTestCase(unittest.TestCase):
    """Runs the library in bash with a fake curl; "as the user" is logged and run directly (tests are unprivileged)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        curl = self.bin / "curl"
        curl.write_text(FAKE_CURL)
        curl.chmod(0o755)
        self.log = self.tmp / "curl.log"
        self.as_user_log = self.tmp / "as-user.log"
        self.fails = self.tmp / "fails"
        self.downloads = self.tmp / "Downloads"
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.work = self.tmp / "work"
        self.work.mkdir(mode=0o700)

    def bash(self, script, fails=0, payload=PAYLOAD, sha=GOOD):
        self.fails.write_text(str(fails))
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", FAKE_LOG=str(self.log),
                   FAKE_FAILS_FILE=str(self.fails), FAKE_PAYLOAD=payload.decode())
        # "As the user" logs the command and runs it (tests are unprivileged).
        prelude = (f'set -euo pipefail\nshopt -s nullglob\nsource "{LIB}"\n'
                   f'xampp_as_user() {{ printf "%s\\n" "$1" >> "{self.as_user_log}"; "$@"; }}\n'
                   f'XAMPP_RETRY_PAUSE=0\n'
                   + (f"XAMPP_SHA256={sha}\n" if sha else ""))
        return subprocess.run(["bash", "-c", prelude + script], env=env, capture_output=True, text=True)

    def as_user(self):
        return self.as_user_log.read_text().split() if self.as_user_log.exists() else []

    def curl_calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def put(self, folder, name, data=PAYLOAD):
        folder.mkdir(exist_ok=True)
        (folder / name).write_bytes(data)
        return folder / name


class PinnedValuesTest(LibTestCase):
    def test_pinned_values(self):
        proc = self.bash('echo "$XAMPP_VERSION $XAMPP_FILE $XAMPP_URL $XAMPP_SHA256"', sha=None)
        version, file, url, sha = proc.stdout.split()
        self.assertEqual(file, PINNED)
        self.assertIn(version, file)
        self.assertTrue(url.startswith("https://downloads.sourceforge.net/"))
        self.assertTrue(url.endswith(f"/{version}/{file}"))
        self.assertRegex(sha, r"^[0-9a-f]{64}$")

    def test_as_user_uses_runuser_for_the_sudo_caller(self):
        text = LIB.read_text()
        self.assertIn('runuser -u "$REAL_USER" --', text)


class FindInstallerTest(LibTestCase):
    def find(self):
        return self.bash(f'xampp_find_installer "{self.project}" "{self.downloads}"')

    def test_pinned_file_wins_over_a_name_that_sorts_later(self):
        self.put(self.downloads, "xampp-linux-x64-8.2.4-0-installer.run")
        pinned = self.put(self.downloads, PINNED)
        self.assertEqual(self.find().stdout.strip(), str(pinned))

    def test_pinned_file_in_the_project_folder_wins(self):
        self.put(self.downloads, "xampp-linux-x64-8.1.25-0-installer.run")
        pinned = self.put(self.project, PINNED)
        self.assertEqual(self.find().stdout.strip(), str(pinned))

    def test_other_versions_and_partial_downloads_are_never_picked(self):
        self.put(self.downloads, "xampp-linux-x64-99.0-0-installer.run")
        self.put(self.project, "xampp-linux-x64-8.1.25-0-installer.run")
        self.put(self.downloads, PINNED + ".part")
        proc = self.find()
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")

    def test_other_installers_are_listed_for_the_hint(self):
        other = self.put(self.downloads, "xampp-linux-x64-8.1.25-0-installer.run")
        self.put(self.downloads, "xampp-linux-x64-evil\x1b[2J-installer.run")
        self.put(self.downloads, PINNED + ".part")
        proc = self.bash(f'xampp_other_installers "{self.project}" "{self.downloads}"')
        self.assertEqual(proc.stdout.splitlines(), [str(other)])


class DownloadTest(LibTestCase):
    def test_download_writes_the_file_with_safe_curl_options(self):
        dest = self.downloads / PINNED
        proc = self.bash(f'xampp_download "{dest}"')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(dest.read_bytes(), PAYLOAD)
        self.assertFalse((self.downloads / (PINNED + ".part")).exists())
        args = self.curl_calls()[0]
        self.assertTrue(args.startswith("-q "), args)  # ~/.curlrc is ignored
        self.assertEqual(proc.stdout, "")
        for flag in ("--fail", "--location", "--proto =https", "--proto-redir =https", "--tlsv1.2",
                     "--connect-timeout", "--speed-limit", "--speed-time", "--continue-at -"):
            self.assertIn(flag, args)

    def test_a_dropped_connection_is_retried_and_resumed(self):
        dest = self.downloads / PINNED
        proc = self.bash(f'xampp_download "{dest}"', fails=2)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(self.curl_calls()), 3)
        self.assertTrue(all("--continue-at -" in call for call in self.curl_calls()))
        self.assertEqual(dest.read_bytes(), PAYLOAD)  # no bytes duplicated across attempts

    def test_curl_output_never_reaches_stdout(self):
        noisy = self.bin / "curl"
        noisy.write_text(FAKE_CURL.replace('printf \'%s\\n\' "$*" >> "$FAKE_LOG"',
                                           'printf \'%s\\n\' "$*" >> "$FAKE_LOG"; echo write-out-noise'))
        proc = self.bash(f'xampp_download "{self.downloads / PINNED}"')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertIn("write-out-noise", proc.stderr)

    def test_everything_in_the_users_folder_runs_as_the_user(self):
        self.bash(f'xampp_download "{self.downloads / PINNED}"', fails=99)
        self.assertEqual(self.as_user(), ["mkdir"] + ["curl"] * 4 + ["rm"])
        self.as_user_log.unlink()
        self.bash(f'xampp_download "{self.downloads / PINNED}"')
        self.assertEqual(self.as_user(), ["mkdir", "curl", "mv"])

    def test_giving_up_leaves_nothing_behind(self):
        dest = self.downloads / PINNED
        (self.downloads).mkdir()
        (self.downloads / (PINNED + ".part")).write_bytes(b"half")
        proc = self.bash(f'xampp_download "{dest}"', fails=99)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(list(self.downloads.iterdir()), [])
        self.assertIn("internet connection", proc.stderr)

    def test_a_folder_that_cannot_be_created_is_not_blamed_on_the_network(self):
        blocker = self.tmp / "file"
        blocker.write_text("")
        proc = self.bash(f'xampp_download "{blocker}/sub/{PINNED}"')
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.curl_calls(), [])
        self.assertIn("cannot create", proc.stderr)
        self.assertNotIn("internet connection", proc.stderr)


class VerifiedCopyTest(LibTestCase):
    def test_returns_a_private_executable_copy(self):
        src = self.put(self.tmp, PINNED)
        proc = self.bash(f'xampp_verified_copy "{src}" "{self.work}"')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        copy = Path(proc.stdout.strip())
        self.assertEqual(copy.parent, self.work)
        self.assertEqual(copy.read_bytes(), PAYLOAD)
        self.assertTrue(os.access(copy, os.X_OK))
        self.assertEqual(copy.stat().st_mode & 0o077, 0)

    def test_wrong_checksum_is_exit_code_1(self):
        src = self.put(self.tmp, PINNED, b"tampered")
        proc = self.bash(f'xampp_verified_copy "{src}" "{self.work}"')
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(list(self.work.iterdir()), [])
        self.assertTrue(src.exists())

    def test_failed_copy_is_exit_code_2_not_a_checksum_failure(self):
        src = self.put(self.tmp, PINNED)
        proc = self.bash(f'xampp_verified_copy "{src}" "{self.tmp}/missing-dir"')
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(src.exists())


class PrepareTest(LibTestCase):
    """xampp_prepare: the whole find → download → check → private copy decision used by setup.sh."""

    def prepare(self, installer="", **kw):
        return self.bash(f'xampp_prepare "{self.work}" "{self.downloads}" "{installer}" "{self.project}"', **kw)

    def test_nothing_found_downloads_checks_and_returns_the_copy(self):
        proc = self.prepare()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), str(self.work / PINNED))
        self.assertEqual((self.downloads / PINNED).read_bytes(), PAYLOAD)
        self.assertEqual(len(self.curl_calls()), 1)
        self.assertIn("Checksum OK", proc.stderr)

    def test_found_pinned_file_is_used_without_downloading(self):
        self.put(self.downloads, PINNED)
        self.put(self.downloads, "xampp-linux-x64-8.2.4-0-installer.run")
        proc = self.prepare()
        self.assertEqual(proc.stdout.strip(), str(self.work / PINNED))
        self.assertEqual(self.curl_calls(), [])

    def test_another_version_is_not_run_but_named_in_a_hint(self):
        other = self.put(self.downloads, "xampp-linux-x64-8.1.25-0-installer.run", b"other")
        proc = self.prepare()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), str(self.work / PINNED))
        self.assertEqual(len(self.curl_calls()), 1)
        self.assertIn(f"--installer {other}", proc.stderr)

    def test_the_hint_quotes_a_path_with_spaces(self):
        spaced = self.tmp / "my downloads"
        other = self.put(spaced, "xampp-linux-x64-8.1.25-0-installer.run", b"other")
        proc = self.bash(f'xampp_prepare "{self.work}" "{spaced}" "" "{self.project}"')
        self.assertIn("--installer " + str(other).replace(" ", "\\ "), proc.stderr)

    def test_installer_option_runs_another_version_unchecked_from_a_private_copy(self):
        other = self.put(self.tmp, "xampp-linux-x64-8.1.25-0-installer.run", b"other")
        proc = self.prepare(installer=str(other))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        copy = self.work / other.name
        self.assertEqual(proc.stdout.strip(), str(copy))
        self.assertEqual(copy.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.curl_calls(), [])

    def test_a_damaged_download_is_deleted(self):
        proc = self.prepare(sha="0" * 64)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        self.assertFalse((self.downloads / PINNED).exists())
        self.assertIn("deleted", proc.stderr)
        self.assertEqual(self.as_user()[-1], "rm")

    def test_a_damaged_file_setup_did_not_download_is_kept(self):
        found = self.put(self.downloads, PINNED, b"tampered")
        proc = self.prepare()
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(found.exists())
        self.assertIn("wrong checksum", proc.stderr)
        self.assertNotIn("has been deleted", proc.stderr)

    def test_a_failed_copy_keeps_the_file_and_says_so(self):
        found = self.put(self.downloads, PINNED)
        proc = self.bash(f'xampp_prepare "{self.tmp}/missing" "{self.downloads}" "" "{self.project}"')
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(found.exists())
        self.assertIn("could not copy", proc.stderr)
        self.assertNotIn("checksum", proc.stderr)

    def test_installer_option_with_a_missing_file(self):
        proc = self.prepare(installer=str(self.tmp / "nope.run"))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not found", proc.stderr)
        self.assertEqual(self.curl_calls(), [])

    def test_installer_option_with_a_dash_name(self):
        odd = self.put(self.tmp, "-x.run", b"other")
        proc = self.bash(f'cd "{self.tmp}" && xampp_prepare "{self.work}" "{self.downloads}" "-x.run" "{self.project}"')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), str(self.work / "-x.run"))
        self.assertTrue(odd.exists())


if __name__ == "__main__":
    unittest.main()
