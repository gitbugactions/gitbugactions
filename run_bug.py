import os
import shutil
import sys
import pygit2
import uuid
import docker
import tempfile
from crawlergpt.test_executor import TestExecutor
from crawlergpt.docker.export import create_act_image
from crawlergpt.actions.workflow import GitHubWorkflowFactory

repo_name = sys.argv[1]
commit = sys.argv[2]
repo_clone_path = sys.argv[3]
exported_dataset_path = sys.argv[4]

repo_clone = pygit2.Repository(os.path.join(repo_clone_path, '.git'))
diff_folder_path = os.path.join(exported_dataset_path, repo_name.replace('/', '-'), commit)
docker_client = docker.from_env()

for path in os.listdir(diff_folder_path):
    if path != "workflow":
        image_name = f"crawlergpt-run-bug:{str(uuid.uuid4())}"
        create_act_image(image_name, os.path.join(diff_folder_path, path))
        # FIXME language
        act_cache_dir = os.path.join(tempfile.gettempdir(), "act-cache", str(uuid.uuid4()))
        executor = TestExecutor(repo_clone, 'java', act_cache_dir, runner=image_name)
        workflow_dir_path = os.path.join(diff_folder_path, 'workflow')
        workflow_name = os.listdir(workflow_dir_path)[0]
        workflow_path = os.path.join(workflow_dir_path, workflow_name)
        
        github_actions_path = os.path.join(repo_clone.workdir, '.github', 'workflows')
        if not os.path.exists(github_actions_path):
            os.makedirs(github_actions_path)
        new_workflow_path = os.path.join(github_actions_path, workflow_name)
        shutil.copyfile(workflow_path, new_workflow_path)

        workflows = [GitHubWorkflowFactory.create_workflow(new_workflow_path, 'java')]
        runs = executor.run_tests(workflows=workflows)
        os.remove(new_workflow_path)
        print(runs)
        docker_client.images.remove(image_name)
        break
