"""Run the fetch, OpenAI composition, and Gmail send pipeline."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"


def run_step(args):
    print(f"==> {' '.join(args)}")
    subprocess.run(args, cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stop-after-fetch",
        action="store_true",
        help="Exit after refreshing output/latest.json.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compose and render the newsletter without sending email.",
    )
    args = parser.parse_args()

    run_step([sys.executable, str(SCRIPTS_DIR / "fetch_headlines.py")])

    if args.stop_after_fetch:
        print("Stopped after fetch as requested.")
        return

    run_step([sys.executable, str(SCRIPTS_DIR / "compose_newsletter.py")])
    metadata_path = ROOT / "output" / "newsletter.json"
    subject = json.loads(metadata_path.read_text(encoding="utf-8"))["subject"]
    if args.dry_run:
        print(f"Dry run complete. Rendered newsletter with subject: {subject}")
        return
    run_step(
        [
            sys.executable,
            str(SCRIPTS_DIR / "send_email.py"),
            "--subject",
            subject,
            "--html-file",
            str(ROOT / "output" / "newsletter.html"),
        ]
    )


if __name__ == "__main__":
    main()
