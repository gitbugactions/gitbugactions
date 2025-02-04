import re
from pathlib import Path
from typing import List, Tuple

from junitparser import TestCase

from gitbugactions.actions.multi.junitxmlparser import JUnitXMLParser
from gitbugactions.actions.workflow import GitHubWorkflow


class CargoWorkflow(GitHubWorkflow):
    BUILD_TOOL_KEYWORDS = ["cargo"]
    # Regex patterns to match cargo test commands
    __COMMAND_PATTERNS = [
        r"cargo\s+(([^\s]+\s+)*)?",
    ]
    GITBUG_CACHE = "~/gitbug-cache"

    def _is_test_command(self, command) -> bool:
        return self.__is_command(command, ["test"])[0]

    def __is_command(self, command: str, keywords: list[str]) -> Tuple[bool, str]:
        # Checks if the given command matches any of the command patterns
        for keyword in keywords:
            for pattern in CargoWorkflow.__COMMAND_PATTERNS:
                if re.search(pattern + keyword, command):
                    return True, keyword
        return False, ""

    def instrument_online_execution(self):
        if self.has_tests():
            for _, job in self.doc["jobs"].items():
                if "steps" in job:
                    for i, step in enumerate(job["steps"]):
                        if "run" in step and self._is_test_command(step["run"]):
                            break
                    else:
                        continue

                    # Job with tests
                    # Install cargo2junit to generate JUnit XML reports
                    job["steps"].insert(
                        i,
                        {
                            "name": "Install cargo2junit",
                            "run": "cargo install cargo2junit",
                        },
                    )
                    # Cache dependencies to speed up builds
                    job["steps"].append(
                        {
                            "name": "Cache dependencies",
                            "run": f"mkdir -p {CargoWorkflow.GITBUG_CACHE} && "
                            + f"cp Cargo.lock {CargoWorkflow.GITBUG_CACHE} || : && "
                            + f"cp Cargo.toml {CargoWorkflow.GITBUG_CACHE} || :",
                        }
                    )
                    job["steps"].insert(0, {"uses": "actions/checkout@v4"})
                    job["steps"].insert(1, {"uses": "dtolnay/rust-toolchain@stable"})
                    return

    def instrument_test_steps(self):
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            step["run"] = step["run"].strip()
                            # see https://github.com/johnterickson/cargo2junit
                            # Ensure the base command starts with RUSTC_BOOTSTRAP=1
                            if not step["run"].startswith("RUSTC_BOOTSTRAP=1"):
                                step["run"] = f"RUSTC_BOOTSTRAP=1 {step['run']}"

                            # Ensure the command uses `--` for test runner arguments
                            if " -- " not in step["run"]:
                                step["run"] = re.sub(
                                    r"(cargo test[^\n]*)", r"\1 --", step["run"]
                                )

                            # Add required test runner arguments if they are not present
                            if "-Z unstable-options" not in step["run"]:
                                step["run"] += " -Z unstable-options"
                            if "--format json" not in step["run"]:
                                step["run"] += " --format json"
                            if "--report-time" not in step["run"]:
                                step["run"] += " --report-time"

                            # Ensure the command pipes to cargo2junit and writes to results.xml
                            if "cargo2junit" not in step["run"]:
                                step["run"] += " | cargo2junit > results.xml"

    def get_test_results(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()
        return parser.get_test_results(str(Path(repo_path, "results.xml")))

    def get_build_tool(self) -> str:
        return "cargo"
