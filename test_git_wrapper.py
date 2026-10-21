#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import tempfile
import unittest


SOURCE = pathlib.Path(__file__).with_name("git.cpp")


class WrapperRoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.tools.name)
        fake = root / "fake_tool.py"
        fake.write_text("""#!/usr/bin/env python3
import json, os, pathlib, sys
kind = 'python' if pathlib.Path(sys.argv[0]).name == 'python' else 'git'
record = {'kind': kind, 'args': sys.argv[1:], 'cwd': os.getcwd()}
with open(pathlib.Path.cwd() / 'calls.jsonl', 'a') as out:
    out.write(json.dumps(record) + '\\n')
raise SystemExit(int(os.environ.get('FAKE_PYTHON_STATUS' if kind == 'python' else 'FAKE_GIT_STATUS', '0')))
""")
        fake.chmod(0o755)
        cls.python = root / "python"
        cls.git = root / "git-real"
        cls.python.symlink_to(fake)
        cls.git.symlink_to(fake)
        cls.repo_helper = root / "git_repo.py"
        cls.submodule_helper = root / "git_submodule.py"
        cls.repo_helper.touch()
        cls.submodule_helper.touch()
        cls.wrapper = root / "git-wrapper"
        macros = {
            "PYTHON_PATH": cls.python,
            "GIT_PATH": cls.git,
            "GIT_REPO_PY_PATH": cls.repo_helper,
            "GIT_REPO_SUBMODULE_PY_PATH": cls.submodule_helper,
        }
        command = [os.environ.get("CXX", "c++"), "-std=c++20", str(SOURCE), "-o", str(cls.wrapper)]
        command += [f'-D{name}={json.dumps(str(value))}' for name, value in macros.items()]
        subprocess.run(command, check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tools.cleanup()

    def invoke(self, *args, cwd=None, env=None):
        return subprocess.run([self.wrapper, *args], cwd=cwd, env=env, text=True,
                              capture_output=True)

    def read_log(self, root):
        path = pathlib.Path(root) / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_clone_recursive_and_explicit_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.invoke("clone", "--recursive", "url", "dest", cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = self.read_log(tmp)
            self.assertEqual(calls[0]["kind"], "python")
            self.assertEqual(calls[0]["args"][1:3], ["--worktree", str(pathlib.Path(tmp) / "dest")])
            self.assertIn("--recursive", calls[0]["args"])
            self.assertEqual(calls[0]["args"][-2:], ["--", "url"])

    def test_unsupported_clone_option_falls_through_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = ["clone", "--depth", "1", "url"]
            result = self.invoke(*original, cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.read_log(tmp), [{"kind": "git", "args": original, "cwd": tmp}])

    def test_chained_C_is_applied_to_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, "a", "b").mkdir(parents=True)
            result = self.invoke("-C", "a", "-C", "b", "init", "repo", cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            call = self.read_log(tmp)[0]
            self.assertEqual(call["args"][3], str(pathlib.Path(tmp, "a", "b", "repo")))

    def test_submodule_add_prewarm_then_original_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = ["submodule", "add", "url", "third party"]
            result = self.invoke(*original, cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = self.read_log(tmp)
            self.assertEqual([c["kind"] for c in calls], ["python", "git"])
            self.assertEqual(calls[1]["args"], original)

    def test_submodule_add_stops_on_helper_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["FAKE_PYTHON_STATUS"] = "7"
            result = self.invoke("submodule", "add", "url", cwd=tmp, env=env)
            self.assertEqual(result.returncode, 7)
            self.assertEqual([c["kind"] for c in self.read_log(tmp)], ["python"])

    def test_submodule_update_gets_working_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.invoke("submodule", "update", "--init", "--recursive", "one", cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            args = self.read_log(tmp)[0]["args"]
            self.assertEqual(args[1:3], ["--working-directory", tmp])
            self.assertIn("--recursive", args)
            self.assertEqual(args[-2:], ["--", "one"])

    def test_semantic_global_option_falls_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = ["-c", "x=y", "clone", "url"]
            result = self.invoke(*original, cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.read_log(tmp)[0]["args"], original)


if __name__ == "__main__":
    unittest.main()
