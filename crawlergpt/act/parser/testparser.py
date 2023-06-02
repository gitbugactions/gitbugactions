from abc import ABC, abstractmethod
from pathlib import Path

import os

class TestParser(ABC):

    @abstractmethod
    def _get_failed_tests(self, file: Path) -> list:
        """Returns a list of failed tests from a test results file"""
        pass
    
    def get_failed_tests(self, filename: str) -> list:
        """Iterates over all files in a directory recursively and returns the aggregated list of test files"""
        failed_tests = []
        file = Path(filename)
        
        if file.is_dir():
            # Iterate over all files in the directory
            for child in file.iterdir():
                failed_tests.extend(self.get_failed_tests(str(child)))
        elif file.exists():
            failed_tests.extend(self._get_failed_tests(file))
                    
        return failed_tests