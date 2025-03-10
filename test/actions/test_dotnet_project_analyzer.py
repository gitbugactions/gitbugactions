import pytest
from unittest.mock import MagicMock, patch

from gitbugactions.actions.csharp.helpers.dotnet_project_analyzer import (
    DotNetProjectAnalyzer,
)


@pytest.fixture
def github_api():
    return MagicMock()


@pytest.fixture
def analyzer(github_api):
    return DotNetProjectAnalyzer(github_api)


def test_is_test_project_file_with_framework_reference(analyzer):
    # Sample .csproj content with test framework reference
    content = """
    <Project Sdk="Microsoft.NET.Sdk">
        <PropertyGroup>
            <TargetFramework>net6.0</TargetFramework>
        </PropertyGroup>
        <ItemGroup>
            <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.0.0" />
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


@patch.object(DotNetProjectAnalyzer, "_find_csproj_files")
@patch.object(DotNetProjectAnalyzer, "_get_file_content")
@patch.object(DotNetProjectAnalyzer, "_list_directory_files")
def test_analyze_repository(
    mock_list_files, mock_get_content, mock_find_csproj, analyzer, github_api
):
    # Mock the GitHub API and repository
    repo = MagicMock()
    github_api.get_repo.return_value = repo

    # Mock finding .csproj files
    mock_find_csproj.return_value = [
        "src/App/App.csproj",
        "src/Core/Core.csproj",
        "tests/UnitTests/UnitTests.csproj",
    ]

    # Mock file contents
    def mock_get_content_side_effect(repo, path):
        if path == "src/App/App.csproj" or path == "src/Core/Core.csproj":
            return """
            <Project Sdk="Microsoft.NET.Sdk">
                <PropertyGroup>
                    <TargetFramework>net6.0</TargetFramework>
                </PropertyGroup>
            </Project>
            """
        elif path == "tests/UnitTests/UnitTests.csproj":
            return """
            <Project Sdk="Microsoft.NET.Sdk">
                <PropertyGroup>
                    <TargetFramework>net6.0</TargetFramework>
                </PropertyGroup>
                <ItemGroup>
                    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.0.0" />
                    <PackageReference Include="xunit" Version="2.4.1" />
                </ItemGroup>
            </Project>
            """
        return None

    mock_get_content.side_effect = mock_get_content_side_effect

    # Mock directory listings
    mock_list_files.return_value = ["Program.cs", "Controller.cs"]

    # Test repository analysis
    source_dirs, test_dirs = analyzer.analyze_repository("owner/repo")

    # Verify results
    assert source_dirs == {"src/App", "src/Core"}
    assert test_dirs == {"tests/UnitTests"}


@patch.object(DotNetProjectAnalyzer, "_find_solution_files")
@patch.object(DotNetProjectAnalyzer, "_analyze_solution_files")
@patch.object(DotNetProjectAnalyzer, "_get_file_content")
@patch.object(DotNetProjectAnalyzer, "_list_directory_files")
def test_analyze_repository_with_solution(
    mock_list_files,
    mock_get_content,
    mock_analyze_solution,
    mock_find_solution,
    analyzer,
    github_api,
):
    # Mock the GitHub API and repository
    repo = MagicMock()
    github_api.get_repo.return_value = repo

    # Mock finding solution files
    mock_find_solution.return_value = ["MySolution.sln"]

    # Mock solution analysis
    mock_analyze_solution.return_value = [
        "src/App/App.csproj",
        "src/Core/Core.csproj",
        "tests/UnitTests/UnitTests.csproj",
    ]

    # Mock file contents
    def mock_get_content_side_effect(repo, path):
        if path == "src/App/App.csproj" or path == "src/Core/Core.csproj":
            return """
            <Project Sdk="Microsoft.NET.Sdk">
                <PropertyGroup>
                    <TargetFramework>net6.0</TargetFramework>
                </PropertyGroup>
            </Project>
            """
        elif path == "tests/UnitTests/UnitTests.csproj":
            return """
            <Project Sdk="Microsoft.NET.Sdk">
                <PropertyGroup>
                    <TargetFramework>net6.0</TargetFramework>
                </PropertyGroup>
                <ItemGroup>
                    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.0.0" />
                    <PackageReference Include="xunit" Version="2.4.1" />
                </ItemGroup>
            </Project>
            """
        return None

    mock_get_content.side_effect = mock_get_content_side_effect

    # Mock directory listings
    mock_list_files.return_value = ["Program.cs", "Controller.cs"]

    # Test repository analysis
    source_dirs, test_dirs = analyzer.analyze_repository("owner/repo")

    # Verify results
    assert source_dirs == {"src/App", "src/Core"}
    assert test_dirs == {"tests/UnitTests"}


def test_analyze_solution_files(analyzer):
    # Mock the repository
    repo = MagicMock()

    # Create a mock solution file content
    solution_content = """
    Microsoft Visual Studio Solution File, Format Version 12.00
    # Visual Studio Version 17
    VisualStudioVersion = 17.0.31903.59
    MinimumVisualStudioVersion = 10.0.40219.1
    Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "App", "src\\App\\App.csproj", "{8AC9E0E8-E84D-4A7F-B15D-7497AEA5E5C9}"
    EndProject
    Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "Core", "src\\Core\\Core.csproj", "{3C4A1FC7-D9C3-4A7F-B15D-7497AEA5E5C9}"
    EndProject
    Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "UnitTests", "tests\\UnitTests\\UnitTests.csproj", "{7F1D64B7-D9C3-4A7F-B15D-7497AEA5E5C9}"
    EndProject
    Global
        GlobalSection(SolutionConfigurationPlatforms) = preSolution
            Debug|Any CPU = Debug|Any CPU
            Release|Any CPU = Release|Any CPU
        EndGlobalSection
    EndGlobal
    """

    # Mock getting file content
    analyzer._get_file_content = MagicMock(return_value=solution_content)

    # Test solution file analysis
    result = analyzer._analyze_solution_files(repo, ["MySolution.sln"])

    # Verify results - should have 3 project paths extracted
    expected_paths = [
        "src/App/App.csproj",
        "src/Core/Core.csproj",
        "tests/UnitTests/UnitTests.csproj",
    ]
    for expected_path in expected_paths:
        assert expected_path in result

    # Should have found all 3 projects
    assert len(result) == 3


@patch.object(DotNetProjectAnalyzer, "_get_file_content")
def test_analyze_workflow_files(mock_get_content, analyzer, github_api):
    # Mock the GitHub API and repository
    repo = MagicMock()
    github_api.get_repo.return_value = repo

    # Mock workflow directory contents
    workflow_content = MagicMock()
    workflow_content.name = "ci.yml"
    workflow_content.path = ".github/workflows/ci.yml"
    repo.get_contents.return_value = [workflow_content]

    # Mock workflow file content
    workflow_yml = """
    name: CI
    on: [push, pull_request]
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
          - name: Test
            run: dotnet test tests/UnitTests
    """
    mock_get_content.return_value = workflow_yml

    # Test workflow analysis
    test_dirs = analyzer.analyze_workflow_files("owner/repo")

    # Verify results
    assert test_dirs == {"tests/UnitTests"}
