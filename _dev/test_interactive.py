import os
import sys
import time

import pexpect

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PYTHON = os.path.join(PROJ_ROOT, ".venv", "bin", "python")

ANSI_ESCAPE = "\x1b["

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def banner(text):
    print(f"\n{'=' * 60}")
    print(f" {BOLD}{text}{RESET}")
    print(f"{'=' * 60}\n")


def strip_ansi(text):
    import re
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)


def test_interactive_menu_preview():
    banner("TEST 1: Interactive → Preview current categories")

    child = pexpect.spawn(
        VENV_PYTHON, ["-m", "star_organizer"],
        cwd=PROJ_ROOT,
        encoding="utf-8",
        timeout=15,
        dimensions=(40, 100),
    )

    try:
        child.expect("What would you like to do", timeout=10)
        print(f"  {GREEN}✓{RESET} Menu prompt appeared")

        time.sleep(0.5)
        for _ in range(4):
            child.send("\x1b[B")
            time.sleep(0.2)

        child.sendline("")
        time.sleep(1)

        child.expect(pexpect.EOF, timeout=10)
        output = strip_ansi(child.before)

        if "No organized stars" in output or "categories" in output.lower():
            print(f"  {GREEN}✓{RESET} Preview mode reached")
        else:
            print(f"  {RED}✗{RESET} Unexpected output after preview selection")

        print(f"\n  {DIM}--- Raw output ---{RESET}")
        for line in output.strip().split("\n")[-8:]:
            print(f"  {DIM}  {line.strip()}{RESET}")

    except pexpect.TIMEOUT:
        print(f"  {RED}✗{RESET} Timed out waiting for menu")
        print(f"  {DIM}Buffer: {strip_ansi(child.before)[:200]}{RESET}")
    finally:
        child.close()


def test_interactive_menu_exit():
    banner("TEST 2: Interactive → Exit")

    child = pexpect.spawn(
        VENV_PYTHON, ["-m", "star_organizer"],
        cwd=PROJ_ROOT,
        encoding="utf-8",
        timeout=15,
        dimensions=(40, 100),
    )

    try:
        child.expect("What would you like to do", timeout=10)
        print(f"  {GREEN}✓{RESET} Menu prompt appeared")

        time.sleep(0.5)
        for _ in range(5):
            child.send("\x1b[B")
            time.sleep(0.2)

        child.sendline("")
        time.sleep(1)

        child.expect(pexpect.EOF, timeout=10)
        output = strip_ansi(child.before)

        if "goodbye" in output.lower() or child.exitstatus == 0:
            print(f"  {GREEN}✓{RESET} Clean exit")
        else:
            print(f"  {RED}✗{RESET} Exit not clean (status={child.exitstatus})")

        print(f"\n  {DIM}--- Raw output ---{RESET}")
        for line in output.strip().split("\n")[-5:]:
            print(f"  {DIM}  {line.strip()}{RESET}")

    except pexpect.TIMEOUT:
        print(f"  {RED}✗{RESET} Timed out")
        print(f"  {DIM}Buffer: {strip_ansi(child.before)[:200]}{RESET}")
    finally:
        child.close()


def test_interactive_organize_only():
    banner("TEST 3: Interactive → Organize only → limit 5 repos")
    print(f"  {DIM}(This will run the actual pipeline with 5 repos — takes ~30s){RESET}")

    child = pexpect.spawn(
        VENV_PYTHON, ["-m", "star_organizer"],
        cwd=PROJ_ROOT,
        encoding="utf-8",
        timeout=120,
        dimensions=(50, 100),
    )

    try:
        child.expect("What would you like to do", timeout=10)
        print(f"  {GREEN}✓{RESET} Menu appeared")

        time.sleep(0.3)
        child.send("\x1b[B")
        time.sleep(0.2)
        child.sendline("")
        print(f"  {GREEN}✓{RESET} Selected 'Organize only'")

        child.expect("Limit repos", timeout=10)
        print(f"  {GREEN}✓{RESET} Limit prompt appeared")

        child.send("\x08")
        time.sleep(0.1)
        child.sendline("5")
        print(f"  {GREEN}✓{RESET} Entered limit: 5")

        child.expect(pexpect.EOF, timeout=90)
        output = strip_ansi(child.before)

        checks = {
            "Phase 1": "Phase 1" in output,
            "Phase 2": "Phase 2" in output,
            "Phase 3": "Phase 3" in output,
            "Done/Summary": "Done" in output or "complete" in output.lower() or "categories" in output.lower(),
        }

        for label, passed in checks.items():
            status = f"{GREEN}✓{RESET}" if passed else f"{RED}✗{RESET}"
            print(f"  {status} {label} output found")

        print(f"\n  {DIM}--- Last 15 lines of output ---{RESET}")
        lines = output.strip().split("\n")
        for line in lines[-15:]:
            print(f"  {DIM}  {line.strip()}{RESET}")

    except pexpect.TIMEOUT:
        print(f"  {RED}✗{RESET} Timed out during pipeline")
        output = strip_ansi(child.before)
        print(f"\n  {DIM}--- Buffer at timeout ---{RESET}")
        for line in output.strip().split("\n")[-10:]:
            print(f"  {DIM}  {line.strip()}{RESET}")
    finally:
        child.close()


def test_flag_help():
    banner("TEST 4: --help flag (non-interactive)")

    child = pexpect.spawn(
        VENV_PYTHON, ["-m", "star_organizer", "--help"],
        cwd=PROJ_ROOT,
        encoding="utf-8",
        timeout=15,
        dimensions=(40, 100),
    )

    try:
        child.expect(pexpect.EOF, timeout=10)
        output = strip_ansi(child.before)

        checks = {
            "--reset": "--reset" in output,
            "--organize-only": "--organize-only" in output,
            "--interactive": "--interactive" in output,
            "--test-limit": "--test-limit" in output,
        }

        for label, passed in checks.items():
            status = f"{GREEN}✓{RESET}" if passed else f"{RED}✗{RESET}"
            print(f"  {status} {label} in help output")

    except pexpect.TIMEOUT:
        print(f"  {RED}✗{RESET} --help timed out")
    finally:
        child.close()


if __name__ == "__main__":
    banner("Star Organizer — Interactive UX Tests (via pexpect)")

    test_flag_help()
    test_interactive_menu_exit()
    test_interactive_menu_preview()
    test_interactive_organize_only()

    print(f"\n{'=' * 60}")
    print(f" {BOLD}Interactive UX testing complete{RESET}")
    print(f"{'=' * 60}\n")
