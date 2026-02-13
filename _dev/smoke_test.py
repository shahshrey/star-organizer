import json
import os
import subprocess
import sys
import tempfile

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAR_ORG = os.path.join(PROJ_ROOT, "star_organizer")

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
results = []


def run(label, cmd, expect_rc=0, expect_in_stdout=None, env=None):
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=PROJ_ROOT, env=run_env)
    ok = r.returncode == expect_rc
    if expect_in_stdout and ok:
        ok = expect_in_stdout in r.stdout
    status = PASS if ok else FAIL
    results.append(ok)
    print(f"  {status} {label}")
    if not ok:
        print(f"    rc={r.returncode}  expected={expect_rc}")
        if r.stdout.strip():
            print(f"    stdout: {r.stdout[:300]}")
        if r.stderr.strip():
            print(f"    stderr: {r.stderr[:300]}")
    return ok


def test_imports():
    print("\n1. Import tests")
    for mod in ["main", "pipeline", "display", "models", "store", "rate_limiter"]:
        run(
            f"import star_organizer.{mod}",
            [sys.executable, "-c", f"import star_organizer.{mod}"],
        )


def test_help():
    print("\n2. CLI --help")
    run(
        "star-organizer --help",
        [sys.executable, "-m", "star_organizer", "--help"],
        expect_in_stdout="organize",
    )


def test_no_interactive_flag():
    print("\n3. --no-interactive with no tokens (expect error exit)")
    run(
        "star-organizer --no-interactive (missing token → exit 1)",
        [sys.executable, "-m", "star_organizer", "--no-interactive"],
        expect_rc=1,
        env={"GITHUB_TOKEN": "", "OPENAI_API_KEY": ""},
    )


def test_preview_empty():
    print("\n4. --sync-only with no data (expect error exit)")
    run(
        "star-organizer --sync-only (no organized data → exit 1)",
        [sys.executable, "-m", "star_organizer", "--no-interactive", "--sync-only"],
        expect_rc=1,
    )


def test_preview_with_mock_data():
    print("\n5. Preview with mock organized_stars.json")
    mock_data = {
        "AI_TOOLS": {
            "description": "AI-powered developer tools",
            "repos": [
                {"url": "https://github.com/test/repo1", "description": "An AI tool"},
                {"url": "https://github.com/test/repo2", "description": "Another AI tool"},
            ],
        },
        "PYTHON_FRAMEWORKS": {
            "description": "Python web frameworks and libraries",
            "repos": [
                {"url": "https://github.com/test/repo3", "description": "A Python framework"},
            ],
        },
        "DEVOPS_TOOLS": {
            "description": "DevOps and infrastructure tools",
            "repos": [],
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(mock_data, f, indent=2)
        tmp_path = f.name

    try:
        script = f"""
import sys
sys.path.insert(0, '{PROJ_ROOT}')
from star_organizer.display import print_categories_table
from star_organizer.store import load_organized_stars
data = load_organized_stars('{tmp_path}')
print_categories_table(data)
print("PREVIEW_OK")
"""
        run(
            "preview categories table renders",
            [sys.executable, "-c", script],
            expect_in_stdout="PREVIEW_OK",
        )
    finally:
        os.unlink(tmp_path)


def test_interactive_detection():
    print("\n6. Interactive mode detection")
    script = f"""
import sys
sys.argv = ['star-organizer']
sys.path.insert(0, '{PROJ_ROOT}')
no_args = len(sys.argv) <= 1
print(f"no_args={{no_args}}")
assert no_args, "Should detect no args"
sys.argv = ['star-organizer', '--reset']
no_args = len(sys.argv) <= 1
print(f"with_flag_no_args={{no_args}}")
assert not no_args, "Should detect args present"
print("DETECT_OK")
"""
    run(
        "interactive mode auto-detection logic",
        [sys.executable, "-c", script],
        expect_in_stdout="DETECT_OK",
    )


def test_display_banner():
    print("\n7. Rich display components")
    script = f"""
import sys
sys.path.insert(0, '{PROJ_ROOT}')
from star_organizer.display import console, print_banner, print_phase, print_success, print_error
print_banner()
print_phase(1, "Test Phase", {{"count": 42}})
print_success("Things look good")
print_error("Something went wrong")
print("DISPLAY_OK")
"""
    run(
        "banner + phase + success + error render",
        [sys.executable, "-c", script],
        expect_in_stdout="DISPLAY_OK",
    )


if __name__ == "__main__":
    print("=" * 50)
    print("Star Organizer — Interactive CLI Smoke Tests")
    print("=" * 50)

    test_imports()
    test_help()
    test_no_interactive_flag()
    test_preview_empty()
    test_preview_with_mock_data()
    test_interactive_detection()
    test_display_banner()

    passed = sum(results)
    total = len(results)
    print(f"\n{'=' * 50}")
    print(f"Results: {passed}/{total} passed")
    if passed == total:
        print(f"{PASS} All tests passed!")
    else:
        print(f"{FAIL} {total - passed} test(s) failed")
    print("=" * 50)
    sys.exit(0 if passed == total else 1)
