from crawlergpt.actions.workflow import GitHubWorkflowFactory
from crawlergpt.actions.java.maven_workflow import MavenWorkflow
from crawlergpt.actions.python.pytest_workflow import PytestWorkflow
from crawlergpt.github_token import GithubToken

import os
import pytest


def create_workflow(yml_file, language):
    """Create a workflow object."""
    return GitHubWorkflowFactory.create_workflow(yml_file, language)


@pytest.mark.parametrize(
    "yml_file",
    [
        ("test/resources/test_workflows/java/maven_test_repo.yml"),
        ("test/resources/test_workflows/java/maven_flacoco.yml"),
    ],
)
def test_maven(yml_file):
    """Test the workflow factory for maven workflows."""
    workflow = create_workflow(yml_file, "java")
    assert isinstance(workflow, MavenWorkflow)


@pytest.mark.parametrize(
    "yml_file",
    [
        ("test/resources/test_workflows/python/pytest_crawlergpt.yml"),
        ("test/resources/test_workflows/python/pytest_crawlergpt_needs.yml"),
        ("test/resources/test_workflows/python/pytest_crawlergpt_no_needs.yml"),
    ],
)
def test_pytest(yml_file):
    """Test the workflow factory for pytest workflows."""
    workflow = create_workflow(yml_file, "python")
    assert isinstance(workflow, PytestWorkflow)


@pytest.mark.parametrize(
    "yml_file",
    [("test/resources/test_workflows/python/pytest_crawlergpt_needs.yml")],
)
def test_pytest_needs(yml_file):
    """Test that the workflow is created and both jobs are kept."""
    workflow = create_workflow(yml_file, "python")
    assert isinstance(workflow, PytestWorkflow)
    workflow.instrument_jobs()
    assert "jobs" in workflow.doc
    assert "setup" in workflow.doc["jobs"]
    assert "test" in workflow.doc["jobs"]
    assert "checkout" in workflow.doc["jobs"]


@pytest.mark.parametrize(
    "yml_file",
    [("test/resources/test_workflows/python/pytest_crawlergpt_no_needs.yml")],
)
def test_pytest_no_needs(yml_file):
    """Test that the workflow is created and only the tests job is kept."""
    workflow = create_workflow(yml_file, "python")
    assert isinstance(workflow, PytestWorkflow)
    workflow.instrument_jobs()
    assert "jobs" in workflow.doc
    assert "setup" not in workflow.doc["jobs"]
    assert "checkout" not in workflow.doc["jobs"]
    assert "test" in workflow.doc["jobs"]


@pytest.mark.parametrize(
    "yml_file",
    [("test/resources/test_workflows/java/maven_cache.yml")],
)
def test_instrument_cache_steps(yml_file):
    workflow = create_workflow(yml_file, "java")
    assert isinstance(workflow, MavenWorkflow)
    workflow.instrument_cache_steps()
    assert len(workflow.doc["jobs"]["build"]["steps"]) == 5
    assert workflow.doc["jobs"]["build"]["steps"][1]["name"] == "Set up JDK 8"
    assert "cache" not in workflow.doc["jobs"]["build"]["steps"][1]["with"]


@pytest.fixture
def teardown_instrument_steps():
    yield
    if os.environ["GITHUB_ACCESS_TOKEN"] == "test":
        os.environ.pop("GITHUB_ACCESS_TOKEN")
        GithubToken.init_tokens()


def test_instrument_steps(teardown_instrument_steps, mocker):
    def update_rate_limit(token):
        token.remaining = 5000

    mocker.patch.object(GithubToken, "update_rate_limit", update_rate_limit)

    workflow = create_workflow(
        "test/resources/test_workflows/java/maven_test_repo.yml", "java"
    )
    if "GITHUB_ACCESS_TOKEN" not in os.environ:
        os.environ["GITHUB_ACCESS_TOKEN"] = "test"

    workflow.instrument_setup_steps()
    assert "token" in workflow.doc["jobs"]["test"]["steps"][1]["with"]
    assert (
        workflow.tokens[0].token
        == workflow.doc["jobs"]["test"]["steps"][1]["with"]["token"]
    )

    workflow.doc["jobs"]["test"]["steps"][1].pop("with")
    assert "with" not in workflow.doc["jobs"]["test"]["steps"][1]
    workflow.instrument_setup_steps()
    assert (
        workflow.tokens[0].token
        == workflow.doc["jobs"]["test"]["steps"][1]["with"]["token"]
    )


@pytest.mark.parametrize(
    "yml_file, language, container_name",
    [
        (
            "test/resources/test_workflows/java/maven_cache.yml",
            "java",
            "act-Java-Main-Workflow-build-1-9a2f0d1cff768c8b7229e206e79ab3f66e613ad6d00562539d8fbd3480f85826",
        ),
        (
            "test/resources/test_workflows/java/maven_matrix.yml",
            "java",
            "act-99e740e7-f7be-412c-8d94-b60b1387fdb0-build-680d85fc5f39b2571eb5a0ca0e1571a5e5a45608294b2e921d181fcdc586f0f3",
        ),
        (
            "test/resources/test_workflows/go/go_matrix.yml",
            "go",
            "act-CI-Run-test-cases-1-4495991e7596ad16a5252e73f0124600806d257360114e99d51859726213778f",
        ),
        (
            "test/resources/test_workflows/python/pytest_crawlergpt.yml",
            "python",
            "act-Tests-build-8e89c69a8459abc0338d6c70c0b0c3bea705ce92f94e8f8b4eb7854e9a11fcf9",
        ),
        (
            "test/resources/test_workflows/go/go_matrix_single.yml",
            "go",
            "act-tests-d7ad1375-9963-419c-abf0-67b3c3567e70-cfbabdb24b3c951e12316ec1a6d9052efac3828dfb651277cec076b3551dbcfa",
        ),
    ],
)
def test_workflow_container_names(yml_file, language, container_name):
    workflow = create_workflow(yml_file, language)

    container_names = workflow.get_container_names()
    assert len(container_names) == 1

    assert container_names[0] == container_name


@pytest.mark.parametrize(
    "yml_file, language, expected_result",
    [
        (
            "test/resources/test_workflows/java/maven_matrix.yml",
            "java",
            False,
        ),
        (
            "test/resources/test_workflows/java/maven_matrix_include.yml",
            "java",
            True,
        ),
    ],
)
def test_workflow_matrix_include_exclude(yml_file, language, expected_result):
    workflow = create_workflow(yml_file, language)

    assert workflow.has_matrix_include_exclude() == expected_result
