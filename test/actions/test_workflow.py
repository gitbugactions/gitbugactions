from gitbugactions.actions.workflow import GitHubWorkflowFactory
from gitbugactions.actions.java.maven_workflow import MavenWorkflow
from gitbugactions.actions.python.pytest_workflow import PytestWorkflow
from gitbugactions.actions.go.go_workflow import GoWorkflow
from gitbugactions.github_api import GithubToken

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
        ("test/resources/test_workflows/python/pytest_gitbugactions.yml"),
        ("test/resources/test_workflows/python/pytest_gitbugactions_needs.yml"),
        ("test/resources/test_workflows/python/pytest_gitbugactions_no_needs.yml"),
    ],
)
def test_pytest(yml_file):
    """Test the workflow factory for pytest workflows."""
    workflow = create_workflow(yml_file, "python")
    assert isinstance(workflow, PytestWorkflow)


@pytest.mark.parametrize(
    "yml_file",
    [("test/resources/test_workflows/python/pytest_gitbugactions_needs.yml")],
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
    [("test/resources/test_workflows/python/pytest_gitbugactions_no_needs.yml")],
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


@pytest.mark.parametrize(
    "yml_file",
    [("test/resources/test_workflows/go/go_on_pull_request.yml")],
)
def test_instrument_on_events(yml_file):
    workflow = create_workflow(yml_file, "go")
    assert isinstance(workflow, GoWorkflow)
    workflow.instrument_on_events()
    assert workflow.doc["on"] == "push"


@pytest.mark.parametrize(
    "yml_file",
    [("test/resources/test_workflows/go/go_vendor.yml")],
)
def test_instrument_vendor(yml_file):
    workflow = create_workflow(yml_file, "go")
    assert isinstance(workflow, GoWorkflow)
    workflow.instrument_test_steps()
    workflow.instrument_offline_execution()

    assert len(workflow.doc["jobs"]["run-tests"]["steps"]) == 5
    assert (
        workflow.doc["jobs"]["run-tests"]["steps"][0]["run"]
        == f"cp -r {GoWorkflow.GITBUG_CACHE}/vendor . || : && cp {GoWorkflow.GITBUG_CACHE}/go.mod . || : && cp {GoWorkflow.GITBUG_CACHE}/go.sum . || :"
    )
    assert (
        workflow.doc["jobs"]["run-tests"]["steps"][-1]["run"]
        == "go test -v ./... -coverprofile=coverage.txt -mod=vendor -covermode=atomic 2>&1 | ~/go/bin/go-junit-report > report.xml"
    )
    assert (
        workflow.doc["jobs"]["run-tests"]["steps"][-2]["run"]
        == "go test -v ./... -coverprofile=coverage.txt -mod=vendor -covermode=atomic 2>&1 | ~/go/bin/go-junit-report > report.xml"
    )

    workflow = create_workflow(yml_file, "go")
    assert isinstance(workflow, GoWorkflow)
    workflow.instrument_offline_execution()

    assert len(workflow.doc["jobs"]["run-tests"]["steps"]) == 5
    assert (
        workflow.doc["jobs"]["run-tests"]["steps"][0]["run"]
        == f"cp -r {GoWorkflow.GITBUG_CACHE}/vendor . || : && cp {GoWorkflow.GITBUG_CACHE}/go.mod . || : && cp {GoWorkflow.GITBUG_CACHE}/go.sum . || :"
    )


@pytest.mark.parametrize(
    "yml_file",
    [("test/resources/test_workflows/go/go_on_pull_request.yml")],
)
def test_instrument_vendor_repeat(yml_file):
    workflow = create_workflow(yml_file, "go")
    assert isinstance(workflow, GoWorkflow)

    workflow.instrument_test_steps()
    # We want to make sure that we remove the steps of the online execution
    workflow.instrument_online_execution()

    workflow.instrument_test_steps()
    workflow.instrument_offline_execution()

    assert len(workflow.doc["jobs"]["unit-test"]["steps"]) == 4
    assert (
        workflow.doc["jobs"]["unit-test"]["steps"][0]["run"]
        == f"cp -r {GoWorkflow.GITBUG_CACHE}/vendor . || : && cp {GoWorkflow.GITBUG_CACHE}/go.mod . || : && cp {GoWorkflow.GITBUG_CACHE}/go.sum . || :"
    )
    assert (
        workflow.doc["jobs"]["unit-test"]["steps"][-1]["run"]
        == "go test -mod=vendor -v ./... 2>&1 | ~/go/bin/go-junit-report > report.xml"
    )


@pytest.mark.parametrize(
    "yml_file",
    [("test/resources/test_workflows/go/go_vendor_with_build.yml")],
)
def test_instrument_vendor_build(yml_file):
    workflow = create_workflow(yml_file, "go")
    assert isinstance(workflow, GoWorkflow)

    workflow.instrument_test_steps()
    workflow.instrument_offline_execution()

    assert len(workflow.doc["jobs"]["build"]["steps"]) == 5
    assert (
        workflow.doc["jobs"]["build"]["steps"][0]["run"]
        == f"cp -r {GoWorkflow.GITBUG_CACHE}/vendor . || : && cp {GoWorkflow.GITBUG_CACHE}/go.mod . || : && cp {GoWorkflow.GITBUG_CACHE}/go.sum . || :"
    )
    assert (
        workflow.doc["jobs"]["build"]["steps"][-2]["run"]
        == "go build -mod=vendor -v ./..."
    )
    assert (
        workflow.doc["jobs"]["build"]["steps"][-1]["run"]
        == "go test -mod=vendor -v ./... 2>&1 | ~/go/bin/go-junit-report > report.xml"
    )


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
