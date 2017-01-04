import os, re, shutil, subprocess, sys, tempfile
from . import utils

def simple_call(args, check=True, stderr=None):
    with open(os.devnull, "r+b") as fdevnull:
        if stderr == "/dev/null":
            stderr = fdevnull
        try:
            subprocess.check_call(args, stdin=fdevnull, stderr=stderr)
        except subprocess.CalledProcessError as e:
            if check:
                raise
            return e.returncode

def run_interactive_shell(cwd=".", env=None):
    p = subprocess.Popen([os.environ.get("SHELL", "sh")], cwd=cwd, env=env)
    try:
        return p.wait()
    except:
        p.terminate()
        p.wait()                        # avoid zombies
        raise

def save_tree(files, cwd="."):
    for fn, s in files.items():
        assert re.match("[A-Za-z0-9_-]+$", fn)
        fn = os.path.join(cwd, fn)
        try:
            os.mkdir(os.path.dirname(fn))
        except OSError:
            pass
        with open(fn, "wb") as f:
            f.write(s.encode("utf-8"))

def load_tree(cwd="."):
    files = {}
    for path, dns, bns in os.walk(cwd):
        dns[:] = [dn for dn in dns if not dn.startswith(".")]
        for bn in bns:
            fn = os.path.join(path, bn)
            rfn = os.path.relpath(fn, cwd)
            with open(fn, "rb") as f:
                files[rfn] = f.read().decode("utf-8")
    return files

def interactive_merge(files1, files2, base_files=None, name="file"):
    '''files: {filenameStr: contentsStr}

    Perform an interactive two- or three-way merge via git.'''
    with tempfile.TemporaryDirectory() as tmp_dir:
        merge_fn = os.path.join(tmp_dir, name)

        simple_call(["git", "-C", tmp_dir, "init", "-q"])
        simple_call(["git", "-C", tmp_dir, "config", "user.name", "nobody"])
        simple_call(["git", "-C", tmp_dir, "config", "user.email",
                     "nobody@localhost.localdomain"])

        if base_files is None:
            simple_call(["git", "-C", tmp_dir, "checkout", "-q", "-b", "left"])
            save_tree(files1, cwd=tmp_dir)
            simple_call(["git", "-C", tmp_dir, "add", "."])
            simple_call(["git", "-C", tmp_dir, "commit", "-q", "-m", "left"])
            simple_call(["git", "-C", tmp_dir, "checkout", "-q", "--orphan",
                         "right"])
            simple_call(["git", "-C", tmp_dir, "reset", "--hard"])
            save_tree(files2, cwd=tmp_dir)
            simple_call(["git", "-C", tmp_dir, "add", "."])
            simple_call(["git", "-C", tmp_dir, "commit", "-q", "-m", "right"])
        else:
            simple_call(["git", "-C", tmp_dir, "checkout", "-q", "-b",
                         "right"])
            save_tree(base_files, cwd=tmp_dir)
            simple_call(["git", "-C", tmp_dir, "add", "."])
            simple_call(["git", "-C", tmp_dir, "commit", "-q", "-m", "base"])
            simple_call(["git", "-C", tmp_dir, "checkout", "-q", "-b", "left"])
            save_tree(files1, cwd=tmp_dir)
            simple_call(["git", "-C", tmp_dir, "add", "."])
            simple_call(["git", "-C", tmp_dir, "commit", "-q", "-m", "left"])
            simple_call(["git", "-C", tmp_dir, "checkout", "-q", "right"])
            save_tree(files2, cwd=tmp_dir)
            simple_call(["git", "-C", tmp_dir, "add", "."])
            simple_call(["git", "-C", tmp_dir, "commit", "-q", "-m", "right"])

        simple_call(["git", "-C", tmp_dir, "checkout", "-q", "left"])
        simple_call(["git", "-C", tmp_dir, "checkout", "-q", "-b", "master"])
        if simple_call(["git", "-C", tmp_dir, "merge", "right",
                        "--allow-unrelated-histories", "-m", "merge"],
                       check=False):
            while True:
                sys.stdout.write("Run 'exit' to complete or "
                                 "cancel the merge.\n")
                sys.stdout.flush()
                run_interactive_shell(cwd=tmp_dir)
                if not simple_call(["git", "-C", tmp_dir, "merge", "-q",
                                    "right", "--allow-unrelated-histories",
                                    "-m", "merge"],
                                   check=False, stderr="/dev/null"):
                    break
                sys.stdout.write(
                    "Merge is not complete.\n"
                    "Hint: Fix them up in the work tree, "
                    "and then use 'git add/rm <file>'\n"
                    "      as appropriate to mark resolution "
                    "and make a commit.\n")
                while True:
                    sys.stdout.write("[Q]uit or [C]ontinue merging? ")
                    sys.stdout.flush()
                    response = utils.input().strip().lower()
                    if response and "quit".startswith(response):
                        return
                    elif response and "continue".startswith(response):
                        break
                    sys.stdout.write("Please type either Q or C.\n")

        return load_tree(cwd=tmp_dir)
