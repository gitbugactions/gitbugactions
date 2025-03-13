import os
from enum import Enum
from typing import List

from unidiff import PatchSet


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
        "typescript": {"ts", "tsx"},
        "c#": {"cs"},
        "c++": {"cpp", "cc", "cxx", "hpp", "hh", "hxx", "c", "h"},
        "c": {"cpp", "cc", "cxx", "hpp", "hh", "hxx", "c", "h"},
    }
    test_keywords = {"test", "tests", "__tests__", "Test", "Tests"}
    cpp_test_prefix = {
        "test",
        "tests",
        str(os.path.join("extra", "tests")),
        "unittest",
        "unittests",
        str(os.path.join("src", "test_lib_json")),
    }
    cpp_test_postfix = {".test.cpp", "_test.cpp", ".test.c", "_test.c"}

    if language in ["java", "python", "javascript", "rust", "typescript", "c#"]:
        if any([keyword in file_path.split(os.sep) for keyword in test_keywords]):
            return FileType.TESTS
    if language in ["go"]:
        if "_test.go" in file_path:
            return FileType.TESTS
    if language in ["javascript"]:
        if ".test.js" in file_path:
            return FileType.TESTS
    if language in ["typescript"]:
        if ".test.ts" in file_path:
            return FileType.TESTS
    if language in ["c", "c++"] and file_path != "/dev/null":
        file_path = (
            file_path[2:]
            if file_path.startswith("a/") or file_path.startswith("b/")
            else file_path
        )
        if any(file_path.startswith(prefix) for prefix in cpp_test_prefix) or any(
            file_path.endswith(postfix) for postfix in cpp_test_postfix
        ):
            return FileType.TESTS

    if get_file_extension(file_path) in language_extensions[language]:
        return FileType.SOURCE
    else:
        return FileType.NON_SOURCE
