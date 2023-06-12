from crawlergpt.actions.workflow import GitHubWorkflowFactory
from crawlergpt.actions.java.maven_workflow import MavenWorkflow
from crawlergpt.actions.python.pytest_workflow import PytestWorkflow

import os
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


def test_instrument_steps():
    workflow = create_workflow("test/resources/test_workflows/java/maven_test_repo.yml", "java")
    os.environ['GITHUB_ACCESS_TOKEN'] = 'test'
    workflow.instrument_setup_steps()
    assert 'token' in workflow.doc['jobs']['test']['steps'][1]['with']
    assert 'test' == workflow.doc['jobs']['test']['steps'][1]['with']['token']

    workflow.doc['jobs']['test']['steps'][1].pop('with')
    assert 'with' not in workflow.doc['jobs']['test']['steps'][1]
    workflow.instrument_setup_steps()
    assert 'test' == workflow.doc['jobs']['test']['steps'][1]['with']['token']