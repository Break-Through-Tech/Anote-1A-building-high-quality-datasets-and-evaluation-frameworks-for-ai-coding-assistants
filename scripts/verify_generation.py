"""
verify_generation.py

Runs through every row in data/processed/generation.jsonl, executes its
ground_truth code, and checks that all of its test_cases actually pass.
Reports any rows that fail, so you can catch cleaning/parsing bugs before
moving on to the next dataset.
"""

import json

INPUT_PATH = "data/processed/generation.jsonl"


def check_row(row):
    """Returns (passed: bool, error_message: str or None)."""
    ns = {}
    try:
        exec(row["ground_truth"], ns)
    except Exception as e:
        return False, f"code failed to parse/exec: {e}"

    for tc in row["test_cases"]:
        try:
            exec(tc, ns)
        except AssertionError:
            return False, f"assertion failed: {tc}"
        except Exception as e:
            return False, f"error running test: {tc} -> {e}"

    return True, None


def main():
    total = 0
    passed = 0
    failures = []

    with open(INPUT_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            total += 1

            ok, err = check_row(row)
            if ok:
                passed += 1
            else:
                failures.append((row["id"], err))

    print(f"Checked {total} rows.")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    if failures:
        print("\n--- Failures ---")
        for row_id, err in failures:
            print(f"{row_id}: {err}")


if __name__ == "__main__":
    main()