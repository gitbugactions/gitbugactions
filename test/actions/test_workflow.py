from crawlergpt.actions.workflow import GitHubWorkflowFactory
from crawlergpt.actions.java.maven_workflow import MavenWorkflow
from crawlergpt.actions.python.pytest_workflow import PytestWorkflow
from crawlergpt.github_token import GithubToken

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

@pytest.fixture
def teardown_instrument_steps():
    yield
    if os.environ['GITHUB_ACCESS_TOKEN'] == "test":
        os.environ.pop('GITHUB_ACCESS_TOKEN')
        GithubToken.init_tokens()

def test_instrument_steps(teardown_instrument_steps, mocker):
    def update_rate_limit(token):
        token.remaining = 5000
    mocker.patch.object(GithubToken, 'update_rate_limit', update_rate_limit)
    
    workflow = create_workflow("test/resources/test_workflows/java/maven_test_repo.yml", "java")
    if 'GITHUB_ACCESS_TOKEN' not in os.environ:
        os.environ['GITHUB_ACCESS_TOKEN'] = 'test'

    workflow.instrument_setup_steps()
    assert 'token' in workflow.doc['jobs']['test']['steps'][1]['with']
    assert workflow.tokens[0].token == workflow.doc['jobs']['test']['steps'][1]['with']['token']

    workflow.doc['jobs']['test']['steps'][1].pop('with')
    assert 'with' not in workflow.doc['jobs']['test']['steps'][1]
    workflow.instrument_setup_steps()
    assert workflow.tokens[0].token == workflow.doc['jobs']['test']['steps'][1]['with']['token']