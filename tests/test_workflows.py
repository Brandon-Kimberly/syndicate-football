"""Workflow shell syntax: the gap that bit on kickoff day (2026-09-09).

The force-canonical baseline run did every meaningful thing right -- synced, gated
CANONICAL_OK, committed and pushed the canonical predictions row -- and then died on
its LAST, purely cosmetic step with a bash PARSE error (exit 2): an apostrophe inside a
`${VAR:-default}` expansion ("see the run's Artifacts section") opens a single-quoted
string that never closes. The readiness audit had already named workflow bash as the
one untested surface; it was proven only by live dispatch. This closes it: every bash
`run:` block in every workflow must parse.

Deliberately syntax-only (`bash -n`). It cannot catch logic errors, and it does not try
to -- but a workflow that cannot be PARSED fails 100% of the time, which is exactly the
class worth a mechanical guard.
"""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_DIR = os.path.join(ROOT, ".github", "workflows")

try:
    import yaml
except ImportError:                                    # pragma: no cover
    yaml = None


def _bash_blocks():
    """(file, step name, script) for every block GitHub will run under bash. A job on
    windows-latest defaults to pwsh, so only steps that ask for bash explicitly count
    there; an ubuntu job defaults to bash."""
    out = []
    for name in sorted(os.listdir(WORKFLOW_DIR)):
        if not name.endswith((".yml", ".yaml")):
            continue
        with open(os.path.join(WORKFLOW_DIR, name), encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        for job in (doc.get("jobs") or {}).values():
            windows = "windows" in str(job.get("runs-on", ""))
            for step in job.get("steps") or []:
                script = step.get("run")
                if not script:
                    continue
                shell = step.get("shell")
                if shell == "bash" or (shell is None and not windows):
                    out.append((name, step.get("name", "?"), script))
    return out


@unittest.skipIf(yaml is None, "pyyaml not installed; workflow syntax guard skipped")
class TestWorkflowBashParses(unittest.TestCase):
    def test_every_bash_run_block_parses(self):
        blocks = _bash_blocks()
        self.assertGreater(len(blocks), 10, "found suspiciously few bash blocks to check")
        failures = []
        for fname, step, script in blocks:
            # ${{ ... }} is GitHub template syntax, substituted before bash ever sees it.
            script = re.sub(r"\$\{\{[^}]*\}\}", "X", script)
            try:
                # bytes, not text: text mode would translate \n -> \r\n on Windows and
                # the stray CRs produce bogus parse errors of their own.
                proc = subprocess.run(["bash", "-n", "-"], input=script.encode("utf-8"),
                                      capture_output=True, timeout=30)
            except (FileNotFoundError, subprocess.TimeoutExpired) as ex:  # pragma: no cover
                self.skipTest(f"bash unavailable for the syntax guard ({ex})")
            if proc.returncode != 0:
                failures.append(f"{fname} -> {step}: {proc.stderr.decode(errors='replace').strip()}")
        self.assertEqual(failures, [], "workflow bash that will not parse:\n" + "\n".join(failures))


@unittest.skipIf(yaml is None, "pyyaml not installed; workflow syntax guard skipped")
@unittest.skipUnless(os.name == "nt", "the WSL-launcher trap is Windows-only")
class TestTheSyntaxGuardRunsARealBash(unittest.TestCase):
    """F90 (2026-11-27). On Windows, CreateProcess searches System32 BEFORE PATH, so a bare
    "bash" resolves to C:\\Windows\\System32\\bash.exe -- the WSL launcher, not Git Bash. On a
    machine with a WSL distro it works (this one); on the windows-latest runner there is no
    distro, the launcher exits non-zero with its message on stdout, and the guard above
    reported every block as unparseable with an EMPTY stderr -- on every CI run since at least
    2026-09-16, unseen because F90's other half masked the suite's exit code. The guard must
    be handed an absolute path to a real bash."""

    def test_the_guard_is_not_handed_a_bare_name_windows_resolves_to_wsl(self):
        from unittest import mock
        seen = []
        real_run = subprocess.run

        def spy(argv, *a, **k):
            seen.append(argv[0])
            return real_run(argv, *a, **k)

        with mock.patch("subprocess.run", side_effect=spy):
            try:
                TestWorkflowBashParses("test_every_bash_run_block_parses").test_every_bash_run_block_parses()
            except unittest.SkipTest:
                pass
        self.assertTrue(seen, "the syntax guard ran no bash at all")
        system32 = os.path.normcase(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32"))
        for exe in set(seen):
            self.assertTrue(os.path.isabs(exe),
                            f"guard runs bare {exe!r}; Windows resolves that via System32 (WSL) first")
            self.assertFalse(os.path.normcase(exe).startswith(system32),
                             f"guard runs the WSL launcher {exe!r}")


class TestPwshStepsFailOnAFailedCommand(unittest.TestCase):
    """F90 (2026-11-27). A `run:` block on a windows job defaults to pwsh, and GitHub's pwsh
    wrapper takes the step result from $LASTEXITCODE of the LAST native command only:
    ErrorActionPreference=stop does not apply to native exit codes. So the CI step

        python -m coverage run -m unittest discover tests
        python -m coverage report

    went green whenever the report printed -- including every run since at least 2026-09-16,
    each of which logged `FAILED (failures=1..2[, errors=..])`. The rule: in a pwsh block, a
    native command used as a bare statement on any line but the last must be followed by an
    explicit `$LASTEXITCODE` check."""

    NATIVE = re.compile(r"^\s*(python|py|pip|git|gh|coverage)\b")

    def test_no_pwsh_step_swallows_a_failed_native_command(self):
        offenders = []
        for name in sorted(os.listdir(WORKFLOW_DIR)):
            if not name.endswith((".yml", ".yaml")):
                continue
            with open(os.path.join(WORKFLOW_DIR, name), encoding="utf-8") as f:
                doc = yaml.safe_load(f) if yaml else None
            if doc is None:
                self.skipTest("pyyaml not installed")
            for job in (doc.get("jobs") or {}).values():
                if "windows" not in str(job.get("runs-on", "")):
                    continue
                for step in job.get("steps") or []:
                    script, shell = step.get("run"), step.get("shell")
                    if not script or shell not in (None, "pwsh", "powershell"):
                        continue
                    lines = [ln for ln in script.splitlines() if ln.strip() and not ln.strip().startswith("#")]
                    for i, ln in enumerate(lines[:-1]):
                        if self.NATIVE.match(ln) and "LASTEXITCODE" not in lines[i + 1]:
                            offenders.append(f"{name} -> {step.get('name', '?')}: {ln.strip()[:80]}")
        self.assertEqual(offenders, [],
                         "pwsh steps whose failed native command cannot fail the step:\n"
                         + "\n".join(offenders))


@unittest.skipIf(yaml is None, "pyyaml not installed; workflow syntax guard skipped")
class TestWorkflowBashExitStatus(unittest.TestCase):
    """The second way a cosmetic step kills a good run (2026-09-13).

    `[ "$MODE" = "force-canonical" ] && echo ...` PARSES fine, so the syntax guard above
    passes it. But a test that is false returns 1, and GitHub takes the block's final
    exit status as the STEP result -- so the job-summary step of the first automated
    canonical run that actually proceeded failed with exit 1 after sync, gate, canonical
    report and the committed predictions row had all succeeded. Same shape as the
    kickoff-day parse error: everything that mattered was already done, and the run still
    went red and alarmed.

    The rule is stricter than the bug needs, on purpose. Whether a given occurrence is
    "the last statement" changes the moment someone adds a line below it, so the guard
    does not try to decide which ones are currently safe: a statement-level test-and-run
    in workflow bash must neutralise its own exit status (`|| true`) or be written as an
    `if` block, which is the house style anyway.
    """

    # A test used as a statement: `[ x ] && cmd` / `[[ x ]] && cmd`, at the start of a
    # line (so `cmd1 && [ x ] && cmd2` -- where the status is already someone else's
    # concern -- is out of scope).
    STATEMENT_TEST = re.compile(r"^\s*\[\[?[^]]*\]\]?\s*&&")
    NEUTRALISED = re.compile(r"\|\|\s*(true|:)\s*$")

    def test_no_bare_statement_level_test_and_run(self):
        offenders = []
        for fname, step, script in _bash_blocks():
            for lineno, line in enumerate(script.splitlines(), 1):
                if self.STATEMENT_TEST.match(line) and not self.NEUTRALISED.search(line):
                    offenders.append(f"{fname} -> {step} (line {lineno}): {line.strip()[:90]}")
        self.assertEqual(
            offenders, [],
            "statement-level `[ ... ] && cmd` leaks its exit status into the step result; "
            "use an if block, or append `|| true`:\n" + "\n".join(offenders))


@unittest.skipIf(yaml is None, "pyyaml not installed; workflow syntax guard skipped")
class TestEveryAlarmCanClearItself(unittest.TestCase):
    """An alarm nobody can silence becomes an alarm nobody reads (2026-09-16).

    Four workflows open an `Automation failure: <name>` issue when they fail, and the
    body each one writes promises *"This issue auto-closes when a run succeeds."* Two of
    them could not keep that promise: `canonical-run` and `pages-sample` raised the alarm
    and had no clear-on-success step at all, so their issues sat open until closed by
    hand. Both were -- #8 on 2026-09-13 and #10 on 2026-09-16, each after the underlying
    failure had already been fixed and a later run had gone green.

    That is the same class as F41 and F44: a monitor whose false state is invisible to
    itself. The invariant is the one the issue body already states, so this test just
    holds the workflows to their own words."""

    ALARM = re.compile(r'title="Automation failure: ([a-z0-9-]+)"')

    def _by_file(self):
        out = {}
        for name in sorted(os.listdir(WORKFLOW_DIR)):
            if name.endswith((".yml", ".yaml")):
                with open(os.path.join(WORKFLOW_DIR, name), encoding="utf-8") as f:
                    out[name] = f.read()
        return out

    def test_a_workflow_that_raises_an_alarm_also_clears_it(self):
        missing = []
        for fname, text in self._by_file().items():
            if not self.ALARM.search(text):
                continue
            has_clear = "gh issue close" in text and "if: success()" in text
            if not has_clear:
                missing.append(fname)
        self.assertEqual(
            missing, [],
            "these workflows open an 'Automation failure' issue but never close it on a "
            "later success, while their issue body promises they will: " + ", ".join(missing))

    def test_the_promise_in_the_issue_body_is_the_one_being_tested(self):
        """Guards the test itself: if someone rewrites the body to stop promising
        auto-close, this test should be revisited rather than silently passing."""
        promises = [f for f, t in self._by_file().items()
                    if "auto-closes when a run succeeds" in t]
        self.assertGreaterEqual(len(promises), 2,
                                "the auto-close promise vanished from the alarm bodies; "
                                "re-read TestEveryAlarmCanClearItself before deleting it")


if __name__ == "__main__":
    unittest.main()
