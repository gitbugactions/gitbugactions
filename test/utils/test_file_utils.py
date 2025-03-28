import pytest
from gitbugactions.utils.file_utils import get_file_type, FileType


@pytest.mark.parametrize(
    "language, file_path, expected",
    [
        # Test for source files
        ("python", "src/main.py", FileType.SOURCE),
        ("java", "src/Main.java", FileType.SOURCE),
        ("c++", "src/main.cpp", FileType.SOURCE),
        ("c", "src/main.c", FileType.SOURCE),
        ("typescript", "src/app.ts", FileType.SOURCE),
        ("go", "src/main.go", FileType.SOURCE),
        # Test for test files
        ("python", "tests/test_main.py", FileType.TESTS),
        ("python", "src/__tests__/test_main.py", FileType.TESTS),
        ("java", "tests/TestMain.java", FileType.TESTS),
        ("c++", "tests/main_test.cpp", FileType.TESTS),
        ("c++", "src/main.test.cpp", FileType.TESTS),
        ("c", "src/main_test.c", FileType.TESTS),
        ("go", "src/main_test.go", FileType.TESTS),
        ("javascript", "src/app.test.js", FileType.TESTS),
        ("typescript", "src/app.test.ts", FileType.TESTS),
        # Test for non-source files
        ("python", "docs/readme.txt", FileType.NON_SOURCE),
        ("java", "assets/image.png", FileType.NON_SOURCE),
        ("c++", "build/output.o", FileType.NON_SOURCE),
        ("c++", "/dev/null", FileType.NON_SOURCE),
    ],
)
def test_get_file_type(language, file_path, expected):
    assert get_file_type(language, file_path) == expected
