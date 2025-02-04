import subprocess
from abc import ABC, abstractmethod
from typing import Optional


class FileReader(ABC):
    @abstractmethod
    def read_file(self, path: str) -> Optional[str]:
        """Read the contents of a file at the given path.

        Args:
            path (str): Path to the file to read

        Returns:
            Optional[str]: The file contents as a string, or None if unable to read
        """
        pass


class RegularFileReader(FileReader):
    def read_file(self, path: str) -> Optional[str]:
        try:
            with open(path, "r") as f:
                return f.read()
        except:
            return None


class GitShowFileReader(FileReader):
    def __init__(self, commit_id: str, working_dir: str):
        self.commit_id = commit_id
        self.working_dir = working_dir

    def read_file(self, path: str) -> Optional[str]:
        try:
            run = subprocess.run(
                f"git show {self.commit_id}:{path}",
                cwd=self.working_dir,
                shell=True,
                capture_output=True,
            )
            if run.returncode != 0:
                return None
            return run.stdout.decode("utf-8")
        except:
            return None
