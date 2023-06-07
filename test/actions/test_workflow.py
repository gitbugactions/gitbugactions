from crawlergpt.actions.workflow import GitHubWorkflow, GitHubWorkflowFactory
from crawlergpt.actions.multi.unknown_workflow import UnknownWorkflow
from crawlergpt.actions.java.maven_workflow import MavenWorkflow
from crawlergpt.actions.python.pytest_workflow import PytestWorkflow

import pytest


def create_workflow(yml_file, language):
    """Create a workflow object."""
    return GitHubWorkflowFactory.create_workflow(yml_file, language)


@pytest.mark.parametrize("yml_file", [
    ("test/resources/test_workflows/java/maven_test_repo.yml"),
    ("test/resources/test_workflows/java/maven_flacoco.yml"),
])
def test_maven(yml_file):
    """Test the workflow factory for maven workflows."""
    workflow = create_workflow(yml_file, "java")
    assert isinstance(workflow, MavenWorkflow)


@pytest.mark.parametrize("yml_file", [
    ("test/resources/test_workflows/python/pytest_crawlergpt.yml"),
])
def test_pytest(yml_file):
    """Test the workflow factory for pytest workflows."""
    workflow = create_workflow(yml_file, "python")
    assert isinstance(workflow, PytestWorkflow)