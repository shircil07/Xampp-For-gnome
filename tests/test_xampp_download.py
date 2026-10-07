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

# A curl stand-in: logs its argv, then writes $FAKE_PAYLOAD to the -o file or fails with $FAKE_CURL_EXIT.
FAKE_CURL = """#!/bin/bash
printf '%s\\n' "$*" >> "$FAKE_LOG"
out=""
while (($#)); do [[ $1 == -o || $1 == --output ]] && out=$2; shift; done
[[ -n $out ]] && printf '%s' "$FAKE_PAYLOAD" > "$out"
exit "${FAKE_CURL_EXIT:-0}"
"""


class XamppDownloadTest(unittest.TestCase):
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
        self.downloads = self.tmp / "Downloads"
        self.work = self.tmp / "work"
        self.work.mkdir(mode=0o700)

    def bash(self, script, curl_exit=0, payload=PAYLOAD):
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", FAKE_LOG=str(self.log),
                   FAKE_PAYLOAD=payload.decode(), FAKE_CURL_EXIT=str(curl_exit))
        # Tests run unprivileged: "as the user" just runs the command.
        prelude = f'set -euo pipefail\nsource "{LIB}"\nxampp_as_user() {{ "$@"; }}\n'
        return subprocess.run(["bash", "-c", prelude + script], env=env, capture_output=True, text=True)

    def test_pinned_values(self):
        proc = self.bash('echo "$XAMPP_FILE $XAMPP_URL $XAMPP_SHA256"')
        file, url, sha = proc.stdout.split()
        self.assertEqual(file, "xampp-linux-x64-8.2.12-0-installer.run")
        self.assertTrue(url.startswith("https://") and url.endswith("/" + file))
        self.assertRegex(sha, r"^[0-9a-f]{64}$")

    def test_download_writes_the_file_and_leaves_no_part(self):
        dest = self.downloads / "x.run"
        proc = self.bash(f'xampp_download "{dest}"')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(dest.read_bytes(), PAYLOAD)
        self.assertEqual(list(self.downloads.glob("*.part")), [])
        args = self.log.read_text()
        for flag in ("--fail", "--location", "--proto =https", "--proto-redir =https", "--retry"):
            self.assertIn(flag, args)

    def test_failed_download_leaves_nothing(self):
        dest = self.downloads / "x.run"
        proc = self.bash(f'xampp_download "{dest}"', curl_exit=22)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(dest.exists())
        self.assertEqual(list(self.downloads.glob("*")), [])

    def test_verified_copy_returns_a_private_executable_copy(self):
        src = self.tmp / "x.run"
        src.write_bytes(PAYLOAD)
        proc = self.bash(f'XAMPP_SHA256={GOOD}; xampp_verified_copy "{src}" "{self.work}"')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        copy = Path(proc.stdout.strip())
        self.assertEqual(copy.parent, self.work)
        self.assertEqual(copy.read_bytes(), PAYLOAD)
        self.assertTrue(os.access(copy, os.X_OK))
        self.assertEqual(copy.stat().st_mode & 0o077, 0)

    def test_verified_copy_refuses_a_wrong_checksum(self):
        src = self.tmp / "x.run"
        src.write_bytes(b"tampered")
        proc = self.bash(f'XAMPP_SHA256={GOOD}; xampp_verified_copy "{src}" "{self.work}"')
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(list(self.work.iterdir()), [])
        self.assertTrue(src.exists())  # deleting is the caller's decision


if __name__ == "__main__":
    unittest.main()
