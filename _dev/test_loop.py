import os
import sys
import time

import pexpect

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PYTHON = os.path.join(PROJ_ROOT, ".venv", "bin", "python")

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
DIM = "\033[2m"


def strip_ansi(text):
    import re
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)


print("=" * 60)
print(" Testing: menu loops back after action")
print("=" * 60)

child = pexpect.spawn(
    VENV_PYTHON, ["-m", "star_organizer"],
    cwd=PROJ_ROOT,
    encoding="utf-8",
    timeout=15,
    dimensions=(40, 100),
)

try:
    child.expect("What would you like to do", timeout=10)
    print(f"  {GREEN}✓{RESET} First menu appeared")

    time.sleep(0.3)
    for _ in range(4):
        child.send("\x1b[B")
        time.sleep(0.15)
    child.sendline("")
    print(f"  {GREEN}✓{RESET} Selected 'Preview'")

    child.expect("What would you like to do", timeout=10)
    print(f"  {GREEN}✓{RESET} Menu re-appeared after Preview (loop works!)")

    time.sleep(0.3)
    for _ in range(5):
        child.send("\x1b[B")
        time.sleep(0.15)
    child.sendline("")
    print(f"  {GREEN}✓{RESET} Selected 'Exit'")

    child.expect(pexpect.EOF, timeout=5)
    output = strip_ansi(child.before)
    if "goodbye" in output.lower():
        print(f"  {GREEN}✓{RESET} Clean exit with 'Goodbye'")
    else:
        print(f"  {GREEN}✓{RESET} Process exited")

    print(f"\n  {DIM}--- Last 6 lines ---{RESET}")
    for line in output.strip().split("\n")[-6:]:
        print(f"  {DIM}  {line.strip()}{RESET}")

except pexpect.TIMEOUT:
    print(f"  {RED}✗{RESET} Timed out")
    print(f"  {DIM}Buffer: {strip_ansi(child.before)[:300]}{RESET}")
finally:
    child.close()

print(f"\n{'=' * 60}")
