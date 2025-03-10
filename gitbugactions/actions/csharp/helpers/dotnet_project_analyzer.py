import os
import re
import xml.etree.ElementTree as ET
import base64
from typing import List, Optional, Set, Tuple


class DotNetProjectAnalyzer:
    """
    Helper class for analyzing .NET project structures without cloning the repository.
    Uses GitHub API to examine .csproj files and determine project structure.
    """

    def __init__(self, github_api):
        """
        Initialize with a GitHub API instance.

        Args:
            github_api: Instance of GithubAPI class
        """
        self.github_api = github_api
        self.test_framework_patterns = [
            "xunit",
            "nunit",
            "mstest",
            "testingframework",
            "test.sdk",
        ]

    def is_test_project_file(self, content: str) -> bool:
        """
        Determines if a .csproj file content represents a test project.

        Args:
            content: The XML content of a .csproj file

        Returns:
            bool: True if it's a test project, False otherwise
        """
        try:
            # Parse XML content
            root = ET.fromstring(content)

            # Look for test framework references
            for elem in root.iter():
                # Check for PackageReference with test frameworks
                if elem.tag.endswith("PackageReference"):
                    include_attr = elem.get("Include", "").lower()
                    if any(
                        framework in include_attr
                        for framework in self.test_framework_patterns
                    ):
                        return True

                # Check for explicit IsTestProject property
                if elem.tag.endswith("IsTestProject"):
                    if elem.text and elem.text.strip().lower() == "true":
                        return True

            return False
        except Exception as e:
            print(f"Error parsing project file: {e}")
            return False

    def has_test_file_naming_pattern(self, files: List[str]) -> bool:
        """
        Checks if any files in the directory follow test naming conventions.

        Args:
            files: List of file names in a directory

        Returns:
            bool: True if test files are found, False otherwise
        """
        test_patterns = [r"test\.cs$", r"tests\.cs$", r"test_", r"tests_"]
        for file in files:
            if any(re.search(pattern, file.lower()) for pattern in test_patterns):
                return True
        return False

    def analyze_repository(
        self, repo_name: str, max_files: int = 100
    ) -> Tuple[Set[str], Set[str]]:
        """
        Analyzes a GitHub repository to identify source and test directories.
        Uses multiple strategies to efficiently identify project structure.

        Args:
            repo_name: The repository name in format "owner/repo"
            max_files: Maximum number of files to analyze to prevent rate limiting

        Returns:
            Tuple[Set[str], Set[str]]: Sets of source and test directory paths
        """
        repo = self.github_api.get_repo(repo_name)
        source_dirs = set()
        test_dirs = set()

        # Strategy 1: Check for solution files first as they're usually at the root
        sln_files = self._find_solution_files(repo)
        if sln_files:
            # If we have solution files, analyze them first to get project references
            sln_projects = self._analyze_solution_files(repo, sln_files)
            if sln_projects:
                for project_path in sln_projects[
                    :max_files
                ]:  # Limit to avoid rate limiting
                    try:
                        content = self._get_file_content(repo, project_path)
                        if not content:
                            continue

                        directory = os.path.dirname(project_path)

                        if self.is_test_project_file(content):
                            test_dirs.add(directory)
                        else:
                            # Check directory files for test naming patterns
                            dir_files = self._list_directory_files(repo, directory)
                            if self.has_test_file_naming_pattern(dir_files):
                                test_dirs.add(directory)
                            else:
                                source_dirs.add(directory)
                    except Exception as e:
                        print(f"Error analyzing project file {project_path}: {e}")

                # If we found both source and test dirs from solution analysis, return results
                if source_dirs and test_dirs:
                    return source_dirs, test_dirs

        # Strategy 2: Find all .csproj files if solutions didn't provide enough information
        csproj_files = self._find_csproj_files(repo)

        # Prioritize csproj files with likely test references first to minimize API calls
        prioritized_files = []
        for file_path in csproj_files:
            priority = 0
            if "test" in file_path.lower():
                priority += 2
            if "src" in file_path.lower():
                priority -= 1
            prioritized_files.append((priority, file_path))

        # Sort by priority (higher first)
        prioritized_files.sort(reverse=True)

        # Process prioritized files up to the max_files limit
        for _, file_path in prioritized_files[:max_files]:
            if file_path in sln_projects:  # Skip if already analyzed via solution
                continue

            try:
                # Get the content of the .csproj file
                content = self._get_file_content(repo, file_path)
                if not content:
                    continue

                directory = os.path.dirname(file_path)

                # Check if it's a test project
                if self.is_test_project_file(content):
                    test_dirs.add(directory)
                else:
                    # Check directory files for test naming patterns
                    dir_files = self._list_directory_files(repo, directory)
                    if self.has_test_file_naming_pattern(dir_files):
                        test_dirs.add(directory)
                    else:
                        source_dirs.add(directory)
            except Exception as e:
                print(f"Error analyzing file {file_path}: {e}")

        # Strategy 3: If we still don't have enough information, analyze workflow files
        if not test_dirs:
            workflow_test_dirs = self.analyze_workflow_files(repo_name)
            test_dirs.update(workflow_test_dirs)

        # Strategy 4: Use conventional directory names as fallback
        if not source_dirs and not test_dirs:
            conventional_src_dirs = {"src", "source", "lib", "common", "main"}
            conventional_test_dirs = {"test", "tests", "unittest", "unittests"}

            try:
                root_contents = repo.get_contents("")
                for content in root_contents:
                    if content.type == "dir":
                        if content.name.lower() in conventional_src_dirs:
                            source_dirs.add(content.path)
                        elif content.name.lower() in conventional_test_dirs:
                            test_dirs.add(content.path)
            except Exception as e:
                print(f"Error analyzing root directories: {e}")

        # Remove test directories from source directories (in case of overlap)
        source_dirs = source_dirs - test_dirs

        return source_dirs, test_dirs

    def _analyze_solution_files(self, repo, sln_files: List[str]) -> List[str]:
        """
        Analyzes .sln files to extract project references.

        Args:
            repo: The GitHub repository object
            sln_files: List of .sln file paths

        Returns:
            List[str]: List of project file paths referenced in the solution
        """
        project_paths = []

        for sln_path in sln_files:
            try:
                content = self._get_file_content(repo, sln_path)
                if not content:
                    continue

                # Extract project references using regex (simplified)
                # Pattern matches: Project("{GUID}") = "ProjectName", "Path\To\Project.csproj", "{GUID}"
                pattern = r'Project\([^)]+\)\s*=\s*"[^"]+",\s*"([^"]+)",\s*"[^"]+"'
                matches = re.findall(pattern, content)

                for match in matches:
                    if match.endswith(".csproj"):
                        # Convert Windows paths to Unix paths
                        match = match.replace("\\", "/")
                        # Make path absolute relative to solution directory
                        sln_dir = os.path.dirname(sln_path)
                        if sln_dir:
                            project_path = os.path.normpath(
                                os.path.join(sln_dir, match)
                            )
                        else:
                            project_path = match

                        project_paths.append(project_path)
            except Exception as e:
                print(f"Error parsing solution file {sln_path}: {e}")

        return project_paths

    def _find_csproj_files(self, repo) -> List[str]:
        """
        Finds all .csproj files in a repository using the GitHub API.

        Args:
            repo: The GitHub repository object

        Returns:
            List[str]: List of file paths to .csproj files
        """
        result = []
        try:
            contents = repo.get_contents("")
            while contents:
                file_content = contents.pop(0)
                if file_content.type == "dir":
                    contents.extend(repo.get_contents(file_content.path))
                elif file_content.name.endswith(".csproj"):
                    result.append(file_content.path)
        except Exception as e:
            print(f"Error finding .csproj files: {e}")

        return result

    def _find_solution_files(self, repo) -> List[str]:
        """
        Finds all .sln (solution) files in a repository using the GitHub API.

        Args:
            repo: The GitHub repository object

        Returns:
            List[str]: List of file paths to .sln files
        """
        result = []
        try:
            contents = repo.get_contents("")
            while contents:
                file_content = contents.pop(0)
                if file_content.type == "dir":
                    contents.extend(repo.get_contents(file_content.path))
                elif file_content.name.endswith(".sln"):
                    result.append(file_content.path)
        except Exception as e:
            print(f"Error finding .sln files: {e}")

        return result

    def _get_file_content(self, repo, file_path: str) -> Optional[str]:
        """
        Gets the content of a file from GitHub.

        Args:
            repo: The GitHub repository object
            file_path: Path to the file

        Returns:
            Optional[str]: The file content as string, or None if not found
        """
        try:
            file_content = repo.get_contents(file_path)
            if hasattr(file_content, "content"):
                return base64.b64decode(file_content.content).decode("utf-8")
            return None
        except Exception as e:
            print(f"Error getting file content for {file_path}: {e}")
            return None

    def _list_directory_files(self, repo, directory: str) -> List[str]:
        """
        Lists all files in a directory.

        Args:
            repo: The GitHub repository object
            directory: Path to the directory

        Returns:
            List[str]: List of file names in the directory
        """
        try:
            contents = repo.get_contents(directory)
            return [content.name for content in contents if content.type == "file"]
        except Exception as e:
            print(f"Error listing directory {directory}: {e}")
            return []

    def analyze_workflow_files(self, repo_name: str) -> Set[str]:
        """
        Analyzes GitHub workflow files to identify dotnet test commands.

        Args:
            repo_name: The repository name in format "owner/repo"

        Returns:
            Set[str]: Set of directories referenced in dotnet test commands
        """
        import yaml

        repo = self.github_api.get_repo(repo_name)
        test_dirs = set()

        try:
            # Get workflow files from .github/workflows directory
            workflow_dir = ".github/workflows"
            workflow_contents = repo.get_contents(workflow_dir)

            for content in workflow_contents:
                if content.name.endswith((".yml", ".yaml")):
                    try:
                        yaml_content = self._get_file_content(repo, content.path)
                        if not yaml_content:
                            continue

                        workflow = yaml.safe_load(yaml_content)
                        if "jobs" not in workflow:
                            continue

                        # Extract test directories from dotnet test commands
                        for _, job in workflow["jobs"].items():
                            if "steps" not in job:
                                continue

                            for step in job["steps"]:
                                if "run" not in step:
                                    continue

                                command = step["run"]
                                if "dotnet test" in command:
                                    # Try to extract directory from command
                                    matches = re.findall(
                                        r"dotnet test\s+([^\s]+)", command
                                    )
                                    for match in matches:
                                        if match and not match.startswith("-"):
                                            test_dirs.add(match)
                    except Exception as e:
                        print(f"Error parsing workflow file {content.path}: {e}")
        except Exception as e:
            print(f"Error accessing workflow files: {e}")

        return test_dirs
