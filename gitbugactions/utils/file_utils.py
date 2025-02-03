import os
from unidiff import PatchSet
from typing import List
from enum import Enum


class FileType(Enum):
    SOURCE = 0
    TESTS = 1
    NON_SOURCE = 2


def get_file_extension(file_path: str) -> str:
    return file_path.split(".")[-1] if "." in file_path else file_path.split(os.sep)[-1]


def get_patch_file_extensions(patch: PatchSet) -> List[str]:
    return list(
        {get_file_extension(p.source_file) for p in patch}.union(
            {get_file_extension(p.target_file) for p in patch}
        )
    )


def get_file_type(language: str, file_path: str) -> FileType:
    language_extensions = {
        "java": {"java"},
        "python": {"py"},
        "go": {"go"},
        "javascript": {"js", "cjs", "mjs", "jsx"},
        "rust": {"rs"},
    }
    test_keywords = {"test", "tests", "__tests__"}

    if language in ["java", "python", "javascript", "rust"]:
        if any([keyword in file_path.split(os.sep) for keyword in test_keywords]):
            return FileType.TESTS
    if language in ["go"]:
        if "_test.go" in file_path:
            return FileType.TESTS
    if language in ["javascript"]:
        if ".test.js" in file_path:
            return FileType.TESTS

    if get_file_extension(file_path) in language_extensions[language]:
        return FileType.SOURCE
    else:
        return FileType.NON_SOURCE
