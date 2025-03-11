import os
import pytest
from unittest.mock import patch, MagicMock, mock_open
import tempfile
import shutil

from gitbugactions.actions.csharp.helpers.dotnet_project_analyzer import (
    DotNetProjectAnalyzer,
)


@pytest.fixture
def temp_repo():
    """Create a temporary directory to simulate a repository"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def analyzer(temp_repo):
    """Create an analyzer instance with a temporary repository path"""
    return DotNetProjectAnalyzer(temp_repo)


def test_is_test_project_file_with_framework_reference(analyzer):
    # Sample .csproj content with test framework reference
    content = """
    <Project Sdk="Microsoft.NET.Sdk">
        <PropertyGroup>
            <TargetFramework>net6.0</TargetFramework>
        </PropertyGroup>
        <ItemGroup>
            <PackageReference Include="xunit" Version="2.4.1" />
            <PackageReference Include="xunit.runner.visualstudio" Version="2.4.3" />
        </ItemGroup>
    </Project>
    """
    assert analyzer.is_test_project_file(content)


def test_is_test_project_file_with_property(analyzer):
    # Sample .csproj content with IsTestProject property
    content = """
    <Project Sdk="Microsoft.NET.Sdk">
        <PropertyGroup>
            <TargetFramework>net6.0</TargetFramework>
            <IsTestProject>true</IsTestProject>
        </PropertyGroup>
    </Project>
    """
    assert analyzer.is_test_project_file(content)


def test_is_test_project_file_not_test(analyzer):
    # Sample .csproj content without test indicators
    content = """
    <Project Sdk="Microsoft.NET.Sdk">
        <PropertyGroup>
            <TargetFramework>net6.0</TargetFramework>
            <OutputType>Library</OutputType>
        </PropertyGroup>
        <ItemGroup>
            <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
        </ItemGroup>
    </Project>
    """
    assert not analyzer.is_test_project_file(content)


def test_has_test_file_naming_pattern(analyzer):
    # Test with various file names
    files = [
        "CalculatorTest.cs",
        "UserControllerTests.cs",
        "test_helpers.cs",
        "Calculator.cs",
    ]
    assert analyzer.has_test_file_naming_pattern(files)


def test_has_test_file_naming_pattern_no_match(analyzer):
    # Test with non-test file names
    files = ["Calculator.cs", "UserController.cs", "Program.cs"]
    assert not analyzer.has_test_file_naming_pattern(files)


@patch("os.walk")
@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open)
def test_analyze_repository(
    mock_open_file, mock_exists, mock_walk, analyzer, temp_repo
):
    # Setup mock directory structure
    mock_walk.return_value = [
        (temp_repo, ["src", "tests"], []),
        (os.path.join(temp_repo, "src"), ["App", "Core"], []),
        (os.path.join(temp_repo, "src", "App"), [], ["App.csproj"]),
        (os.path.join(temp_repo, "src", "Core"), [], ["Core.csproj"]),
        (os.path.join(temp_repo, "tests"), ["UnitTests"], []),
        (os.path.join(temp_repo, "tests", "UnitTests"), [], ["UnitTests.csproj"]),
    ]

    # Mock file existence checks
    mock_exists.return_value = True

    # Setup mock file contents
    def mock_read_side_effect(*args, **kwargs):
        # This will be called when the context manager is entered
        mock_file = MagicMock()

        # Get the filename from the first positional argument to open()
        filename = args[0]

        if "App.csproj" in filename or "Core.csproj" in filename:
            mock_file.read.return_value = """
            <Project Sdk="Microsoft.NET.Sdk">
                <PropertyGroup>
                    <TargetFramework>net6.0</TargetFramework>
                </PropertyGroup>
                <ItemGroup>
                    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
                </ItemGroup>
            </Project>
            """
        elif "UnitTests.csproj" in filename:
            mock_file.read.return_value = """
            <Project Sdk="Microsoft.NET.Sdk">
                <PropertyGroup>
                    <TargetFramework>net6.0</TargetFramework>
                </PropertyGroup>
                <ItemGroup>
                    <PackageReference Include="xunit" Version="2.4.1" />
                    <PackageReference Include="xunit.runner.visualstudio" Version="2.4.3" />
                </ItemGroup>
            </Project>
            """

        return mock_file

    mock_open_file.side_effect = mock_read_side_effect

    # Call the method under test
    source_dirs, test_dirs = analyzer.analyze_repository()

    # Verify results
    assert "src/App" in source_dirs
    assert "src/Core" in source_dirs
    assert "tests/UnitTests" in test_dirs


@patch("os.walk")
@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open)
def test_analyze_repository_with_solution(
    mock_open_file, mock_exists, mock_walk, analyzer, temp_repo
):
    # Setup mock directory structure with a solution file
    mock_walk.return_value = [
        (temp_repo, [], ["Solution.sln"]),
        (temp_repo, ["src", "tests"], ["Solution.sln"]),
        (os.path.join(temp_repo, "src"), ["App"], []),
        (os.path.join(temp_repo, "src", "App"), [], ["App.csproj"]),
        (os.path.join(temp_repo, "tests"), [], ["Tests.csproj"]),
    ]

    # Mock file existence checks
    mock_exists.return_value = True

    # Setup mock file contents
    def mock_read_side_effect(*args, **kwargs):
        # This will be called when the context manager is entered
        mock_file = MagicMock()

        # Get the filename from the first positional argument to open()
        filename = args[0]

        if "Solution.sln" in filename:
            mock_file.read.return_value = """
            Microsoft Visual Studio Solution File, Format Version 12.00
            Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "App", "src/App/App.csproj", "{12345678-1234-1234-1234-123456789012}"
            Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "Tests", "tests/Tests.csproj", "{87654321-4321-4321-4321-210987654321}"
            """
        elif "App.csproj" in filename:
            mock_file.read.return_value = """
            <Project Sdk="Microsoft.NET.Sdk">
                <PropertyGroup>
                    <TargetFramework>net6.0</TargetFramework>
                </PropertyGroup>
            </Project>
            """
        elif "Tests.csproj" in filename:
            mock_file.read.return_value = """
            <Project Sdk="Microsoft.NET.Sdk">
                <PropertyGroup>
                    <TargetFramework>net6.0</TargetFramework>
                </PropertyGroup>
                <ItemGroup>
                    <PackageReference Include="xunit" Version="2.4.1" />
                </ItemGroup>
            </Project>
            """

        return mock_file

    mock_open_file.side_effect = mock_read_side_effect

    # Call the method under test
    source_dirs, test_dirs = analyzer.analyze_repository()

    # Verify results
    assert "src/App" in source_dirs
    assert "tests" in test_dirs


@patch("os.walk")
@patch("os.path.exists")
@patch("os.listdir")
@patch("builtins.open", new_callable=mock_open)
def test_analyze_workflow_files(
    mock_open_file, mock_listdir, mock_exists, mock_walk, analyzer, temp_repo
):
    # Mock path existence for the .github/workflows directory
    def mock_exists_side_effect(path):
        if ".github/workflows" in path:
            return True
        return False

    mock_exists.side_effect = mock_exists_side_effect

    # Mock directory listing for the workflows directory
    mock_listdir.return_value = ["build.yml", "test.yml"]

    # Define the file contents
    build_yml_content = """
    name: Build
    
    on:
      push:
        branches: [ main ]
    
    jobs:
      build:
        runs-on: ubuntu-latest
        steps:
        - uses: actions/checkout@v2
        - name: Setup .NET
          uses: actions/setup-dotnet@v1
          with:
            dotnet-version: 6.0.x
        - name: Build
          run: dotnet build
    """

    test_yml_content = """
    name: Test
    
    on:
      push:
        branches: [ main ]
    
    jobs:
      test:
        runs-on: ubuntu-latest
        steps:
        - uses: actions/checkout@v2
        - name: Setup .NET
          uses: actions/setup-dotnet@v1
          with:
            dotnet-version: 6.0.x
        - name: Test
          run: dotnet test
    """

    # Configure the mock to return different content based on the filename
    mock_file_handle = mock_open_file.return_value.__enter__.return_value

    def read_side_effect(*args, **kwargs):
        filename = mock_open_file.call_args[0][0]
        if filename.endswith("build.yml"):
            return build_yml_content
        elif filename.endswith("test.yml"):
            return test_yml_content
        return ""

    mock_file_handle.read.side_effect = read_side_effect

    # Call the method under test
    build_commands = analyzer.analyze_workflow_files()

    # Verify results
    assert "dotnet" in build_commands
