from abc import ABC, abstractmethod
from pathlib import Path

import os

class TestParser(ABC):

    @abstractmethod
    def __get_failed_tests(self, file: Path) -> list:
        """Returns a list of failed tests from a test results file"""
        pass
    
    def get_failed_tests(self, directory: str) -> list:
        """Iterates over all files in a directory recursively and returns the aggregated list of test files"""
        failed_tests = []
        dir = Path(directory)
        
        # Check if dir is a directory
        if dir.is_dir():
            # Iterate over all files in the directory
            for file in dir.iterdir():
                # If it is a directory, call the function recursively
                if file.is_dir():
                    failed_tests.extend(self.get_failed_tests(file))
                # If it is a file, call the __get_failed_tests function
                elif os.path.isfile(file):
                    failed_tests.extend(self.__get_failed_tests(file))
                    
        return failed_tests