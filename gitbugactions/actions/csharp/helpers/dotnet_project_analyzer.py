import os
import re
import xml.etree.ElementTree as ET
from typing import List, Set, Tuple
import logging

logger = logging.getLogger(__name__)


class DotNetProjectAnalyzer:
    """
    Helper class for analyzing .NET project structures using the local file system.
    Examines .csproj files and determines project structure.
    """

    def __init__(self, repo_path: str):
        """
        Initialize with a repository path.

        Args:
            repo_path: Path to the repository root
        """
        self.repo_path = repo_path
        self.test_framework_patterns = [
            "xunit",
            "nunit",
            "mstest",
            "testingframework",
            "test.sdk",
        ]

    def _should_ignore_path(self, path: str) -> bool:
        """
        Check if a path should be ignored during analysis.

        Args:
            path: The path to check

        Returns:
            bool: True if the path should be ignored, False otherwise
        """
        # Normalize path separators for consistent checking
        normalized_path = os.path.normpath(path)
        path_parts = normalized_path.split(os.sep)

        # Check if any part of the path contains .act-result
        return any(".act-result" in part for part in path_parts)

    def is_test_project_file(self, content: str) -> bool:
        """
        Determines if a .csproj file content represents a test project.

        Args:
            content: The XML content of a .csproj file

        Returns:
            bool: True if the project is a test project, False otherwise
        """
        try:
            # Check for test framework references
            for pattern in self.test_framework_patterns:
                if pattern.lower() in content.lower():
                    return True

            # Check for IsTestProject property
            if "<IsTestProject>true</IsTestProject>" in content:
                return True

            # Try to parse XML for more detailed analysis
            try:
                root = ET.fromstring(content)
                # Check for test SDK PackageReference
                for item_group in root.findall(".//ItemGroup"):
                    for ref in item_group.findall(".//PackageReference"):
                        include = ref.get("Include", "")
                        if any(
                            pattern.lower() in include.lower()
                            for pattern in self.test_framework_patterns
                        ):
                            return True
            except ET.ParseError:
                # If XML parsing fails, rely on the string checks above
                pass

            return False
        except Exception as e:
            logger.warning(f"Error analyzing project file: {e}")
            return False

    def has_test_file_naming_pattern(self, files: List[str]) -> bool:
        """
        Check if any files in the directory follow test naming patterns.

        Args:
            files: List of file names

        Returns:
            bool: True if any file matches test naming patterns
        """
        test_patterns = [
            r".*test.*\.cs$",
            r".*spec.*\.cs$",
            r".*fixture.*\.cs$",
        ]

        for file in files:
            file_lower = file.lower()
            if any(re.match(pattern, file_lower) for pattern in test_patterns):
                return True
        return False

    def analyze_repository(self, max_files: int = 1000) -> Tuple[Set[str], Set[str]]:
        """
        Analyze the repository structure to identify source and test directories.

        Args:
            max_files: Maximum number of files to analyze

        Returns:
            Tuple[Set[str], Set[str]]: Sets of source and test directory paths
        """
        source_dirs = set()
        test_dirs = set()

        try:
            # First, look for solution files
            sln_files = self._find_solution_files()
            if sln_files:
                # If solution files exist, analyze them to find project references
                project_files = self._analyze_solution_files(sln_files)
                if project_files:
                    # Process the project files found in solutions
                    for proj_file in project_files:
                        self._process_project_file(proj_file, source_dirs, test_dirs)

            # If no projects were found through solutions, search for .csproj files directly
            if not source_dirs and not test_dirs:
                csproj_files = self._find_csproj_files()
                for proj_file in csproj_files[:max_files]:
                    self._process_project_file(proj_file, source_dirs, test_dirs)

            # If still no directories found, use reasonable defaults
            if not source_dirs and not test_dirs:
                # Look for directories with common naming patterns
                for root, dirs, _ in os.walk(self.repo_path):
                    # Skip directories that should be ignored
                    dirs[:] = [
                        d
                        for d in dirs
                        if not self._should_ignore_path(os.path.join(root, d))
                    ]

                    for dir_name in dirs:
                        rel_path = os.path.relpath(
                            os.path.join(root, dir_name), self.repo_path
                        )
                        if any(
                            test_indicator in rel_path.lower()
                            for test_indicator in ["test", "tests"]
                        ):
                            test_dirs.add(rel_path)
                        elif any(
                            src_indicator in rel_path.lower()
                            for src_indicator in ["src", "source"]
                        ):
                            source_dirs.add(rel_path)

            # If still nothing found, use the repository root
            if not source_dirs:
                source_dirs.add(".")
            if not test_dirs:
                test_dirs.add(
                    "tests"
                    if os.path.exists(os.path.join(self.repo_path, "tests"))
                    else "."
                )

            return source_dirs, test_dirs

        except Exception as e:
            logger.error(f"Error analyzing repository structure: {e}")
            # Return reasonable defaults on error
            return {"src", "."}, {"test", "tests"}

    def _process_project_file(
        self, proj_file: str, source_dirs: Set[str], test_dirs: Set[str]
    ):
        """
        Process a project file to determine if it's a source or test project.

        Args:
            proj_file: Path to the project file
            source_dirs: Set to add source directories to
            test_dirs: Set to add test directories to
        """
        try:
            # Skip files in .act-result directories
            if self._should_ignore_path(proj_file):
                return

            # Get the directory containing the project file
            proj_dir = os.path.dirname(proj_file)
            rel_path = os.path.relpath(proj_dir, self.repo_path)
            rel_path = "." if rel_path == "" else rel_path

            # Check if it's a test project
            is_test = False

            # Check file name for test indicators
            if any(
                test_indicator in os.path.basename(proj_file).lower()
                for test_indicator in ["test", "tests"]
            ):
                is_test = True
            # Check directory name for test indicators
            elif any(
                test_indicator in rel_path.lower()
                for test_indicator in ["test", "tests"]
            ):
                is_test = True
            else:
                # Read the project file content
                try:
                    with open(proj_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        if self.is_test_project_file(content):
                            is_test = True
                except Exception as e:
                    logger.debug(f"Could not read {proj_file}: {e}")

                    # If we can't read the file, check if there are test files in the directory
                    if not is_test:
                        try:
                            files = os.listdir(proj_dir)
                            if self.has_test_file_naming_pattern(files):
                                is_test = True
                        except Exception as e:
                            logger.debug(f"Could not list files in {proj_dir}: {e}")

            # Add to appropriate set
            if is_test:
                test_dirs.add(rel_path)
            else:
                source_dirs.add(rel_path)

        except Exception as e:
            logger.debug(f"Error processing project file {proj_file}: {e}")

    def _analyze_solution_files(self, sln_files: List[str]) -> List[str]:
        """
        Analyze solution files to find project references.

        Args:
            sln_files: List of solution file paths

        Returns:
            List[str]: List of project file paths
        """
        project_files = []

        for sln_file in sln_files:
            # Skip files in .act-result directories
            if self._should_ignore_path(sln_file):
                continue

            try:
                with open(sln_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                    # Extract project references using regex
                    # Format: Project("{GUID}") = "ProjectName", "ProjectPath", "{ProjectGUID}"
                    project_matches = re.findall(
                        r'Project\("\{[^}]+\}"\)\s*=\s*"[^"]+",\s*"([^"]+)"', content
                    )

                    for proj_path in project_matches:
                        if proj_path.endswith(".csproj"):
                            # Convert relative path to absolute
                            sln_dir = os.path.dirname(sln_file)
                            abs_proj_path = os.path.normpath(
                                os.path.join(sln_dir, proj_path)
                            )

                            if os.path.exists(
                                abs_proj_path
                            ) and not self._should_ignore_path(abs_proj_path):
                                project_files.append(abs_proj_path)
            except Exception as e:
                logger.debug(f"Error analyzing solution file {sln_file}: {e}")

        return project_files

    def _find_csproj_files(self) -> List[str]:
        """
        Find all .csproj files in the repository.

        Returns:
            List[str]: List of .csproj file paths
        """
        csproj_files = []

        for root, dirs, files in os.walk(self.repo_path):
            # Skip directories that should be ignored
            dirs[:] = [
                d for d in dirs if not self._should_ignore_path(os.path.join(root, d))
            ]

            # Skip if current directory should be ignored
            if self._should_ignore_path(root):
                continue

            for file in files:
                if file.endswith(".csproj"):
                    file_path = os.path.join(root, file)
                    if not self._should_ignore_path(file_path):
                        csproj_files.append(file_path)

        return csproj_files

    def _find_solution_files(self) -> List[str]:
        """
        Find all .sln files in the repository.

        Returns:
            List[str]: List of .sln file paths
        """
        sln_files = []

        for root, dirs, files in os.walk(self.repo_path):
            # Skip directories that should be ignored
            dirs[:] = [
                d for d in dirs if not self._should_ignore_path(os.path.join(root, d))
            ]

            # Skip if current directory should be ignored
            if self._should_ignore_path(root):
                continue

            for file in files:
                if file.endswith(".sln"):
                    file_path = os.path.join(root, file)
                    if not self._should_ignore_path(file_path):
                        sln_files.append(file_path)

        return sln_files

    def analyze_workflow_files(self) -> Set[str]:
        """
        Analyze workflow files to identify build commands.

        Returns:
            Set[str]: Set of build commands
        """
        build_commands = set()
        workflow_dir = os.path.join(self.repo_path, ".github", "workflows")

        if not os.path.exists(workflow_dir) or self._should_ignore_path(workflow_dir):
            return build_commands

        try:
            for file in os.listdir(workflow_dir):
                if file.endswith((".yml", ".yaml")):
                    file_path = os.path.join(workflow_dir, file)
                    # Skip files in .act-result directories
                    if self._should_ignore_path(file_path):
                        continue

                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()

                            # Look for dotnet build commands
                            build_patterns = [
                                r"dotnet\s+build",
                                r"dotnet\s+test",
                                r"dotnet\s+run",
                                r"dotnet\s+publish",
                                r"msbuild",
                                r"vstest",
                            ]

                            for pattern in build_patterns:
                                if re.search(pattern, content, re.IGNORECASE):
                                    build_commands.add(pattern.split("\\s+")[0])
                    except Exception as e:
                        logger.debug(f"Error reading workflow file {file_path}: {e}")
        except Exception as e:
            logger.debug(f"Error analyzing workflow files: {e}")

        return build_commands
