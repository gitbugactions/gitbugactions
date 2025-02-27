import json
import shutil
from pathlib import Path
import fire
import logging


def organize_bugs(
    collect_bugs_dir: str,
    export_bugs_dir: str,
    filter_bugs_dir: str,
    output_dir: str,
):
    """
    Organize bugs from collection directories into a structured output directory.

    Args:
        collect_bugs_dir: Directory containing collected bug JSON files
        export_bugs_dir: Directory containing exported bug files
        filter_bugs_dir: Directory containing the non-flaky.json file
        output_dir: Output directory for organized bugs (default: 'data')
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Create output directory structure
    output_path = Path(output_dir)
    bugs_dir = output_path / "bugs"
    bugs_dir.mkdir(parents=True, exist_ok=True)
    logging.info(f"Created output directory structure at {output_path}")

    # Read non-flaky bugs
    with open(Path(filter_bugs_dir) / "non-flaky.json", "r") as f:
        non_flaky_bugs = [json.loads(line) for line in f if line.strip()]
    logging.info(f"Loaded {len(non_flaky_bugs)} non-flaky bugs")

    # Group non-flaky bugs by repository
    bugs_by_repo = {}
    for bug in non_flaky_bugs:
        repo = bug["repository"]
        if repo not in bugs_by_repo:
            bugs_by_repo[repo] = []
        bugs_by_repo[repo].append(bug)
    logging.info(f"Found bugs from {len(bugs_by_repo)} repositories")

    # Process each repository
    for repo, bugs in bugs_by_repo.items():
        logging.info(f"Processing repository: {repo}")
        # Convert repository name format (owner/repo -> owner-repo) and lowercase it
        repo_file = repo.replace("/", "-").lower()

        # Read the collection file for this repository
        collect_file = Path(collect_bugs_dir) / f"{repo_file}.json"
        if not collect_file.exists():
            # Try with original case if lowercase file doesn't exist
            original_repo_file = repo.replace("/", "-")
            collect_file = Path(collect_bugs_dir) / f"{original_repo_file}.json"
            if not collect_file.exists():
                logging.warning(f"Collection file not found for {repo}")
                continue

        # Read and filter bug information
        collected_bugs = []
        with open(collect_file, "r") as f:
            for line in f:
                if line.strip():
                    bug_info = json.loads(line)
                    # Skip bugs with change_type of NON_CODE
                    if bug_info.get("change_type") == "NON_CODE":
                        continue
                    # Check if this bug's commit is in our non-flaky list
                    if any(b["commit"] == bug_info["commit_hash"] for b in bugs):
                        collected_bugs.append(bug_info)

        # Save filtered bug information
        if collected_bugs:
            # Save bug information to data/bugs/repo.json (lowercase)
            output_file = bugs_dir / f"{repo_file}.json"
            with open(output_file, "w") as f:
                for bug in collected_bugs:
                    f.write(json.dumps(bug) + "\n")
            logging.info(f"Saved {len(collected_bugs)} bugs for {repo}")

            # Copy export directories for each commit
            for bug in collected_bugs:
                commit = bug["commit_hash"]
                # Try to find source directory with original case first
                original_repo_file = repo.replace("/", "-")
                src_dir = Path(export_bugs_dir) / original_repo_file / commit
                if not src_dir.exists():
                    # Try with lowercased directory
                    src_dir = Path(export_bugs_dir) / repo_file / commit
                    if not src_dir.exists():
                        logging.warning(
                            f"Export directory not found for commit {commit}"
                        )
                        continue

                # Use lowercase for destination directory
                dst_dir = output_path / repo_file / commit.lower()
                dst_dir.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
                logging.info(f"Copied export directory for commit {commit}")


if __name__ == "__main__":
    fire.Fire(organize_bugs)
