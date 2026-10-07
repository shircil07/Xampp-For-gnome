"""Fakes shared by the repair and health tests."""

import re
import subprocess
from pathlib import Path

from xampp_panel.mysqladmin import MysqlError


class FakeDialogs:
    def __init__(self, answers=()):
        self.answers = list(answers)
        self.shown = []

    def _next(self, kind, text):
        self.shown.append((kind, text))
        if not self.answers:
            raise AssertionError(f"no scripted answer for {kind}: {text}")
        return self.answers.pop(0)

    def menu(self, text, items):
        return self._next("menu", text)

    def yesno(self, text):
        return self._next("yesno", text)

    def passwordbox(self, text):
        return self._next("passwordbox", text)

    def msgbox(self, text):
        self.shown.append(("msgbox", text))

    def secret(self, title, text):
        self.shown.append(("secret", text))

    def messages(self):
        return [text for kind, text in self.shown if kind == "msgbox"]

    def secrets(self):
        return [text for kind, text in self.shown if kind == "secret"]


class FakeAdmin:
    """Pretends to be MariaDB: a root password, a control-user login result, recorded SQL."""

    def __init__(self, root_password="", pma_login=True):
        self.root_password = root_password
        self.pma_login = pma_login
        self.executed = []
        self.fail = None
        self.anonymous = ["''@'localhost'"]
        self.connect_error = None  # set: the server does not answer (can_login raises, ping is False)
        self.unready_pings = 0  # ping() answers False this many times first
        self.pings = 0

    def can_login(self, user, password, database=None):
        if self.connect_error:
            raise MysqlError(self.connect_error)
        if user == "root":
            return password == self.root_password
        return self.pma_login

    def ping(self):
        self.pings += 1
        if self.unready_pings:
            self.unready_pings -= 1
            return False
        return not self.connect_error

    def execute(self, sql, root_password):
        if root_password != self.root_password:
            raise MysqlError("ERROR 1045 (28000): Access denied for user 'root'@'localhost'")
        if self.fail:
            raise MysqlError(self.fail)
        self.executed.append(sql)
        if "DROP USER" in sql:
            self.anonymous = []
        m = re.search(r"^SET @pw = '((?:[^']|'')*)';$", sql, re.M)
        if m:
            self.root_password = m[1].replace("''", "'").replace("\\\\", "\\")
        return ""

    def anonymous_accounts(self, root_password):
        return list(self.anonymous)

    def upgrade(self, root_password):
        return "Phase 7/7: Running 'FLUSH PRIVILEGES'\nOK\n"


class FakeHelper:
    def __init__(self):
        self.calls = []

    def lampp(self, actions):
        self.calls.append(("lampp", list(actions)))

    def integrate(self, on):
        self.calls.append(("integrate", on))

    def harden(self, on):
        self.calls.append(("harden", on))

    def lean(self, on):
        self.calls.append(("lean", on))

    def apply_sites(self, sites):
        self.calls.append(("apply", list(sites)))


class FakeRun:
    """subprocess.run stand-in answering by program name: {"openssl": (0, "$6$...\\n", "")}.
    An exception as the answer is raised instead."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(map(str, argv)), kwargs))
        answer = self.answers.get(Path(str(argv[0])).name, (0, "", ""))
        if isinstance(answer, BaseException):
            raise answer
        code, out, err = answer
        return subprocess.CompletedProcess(argv, code, out, err)
