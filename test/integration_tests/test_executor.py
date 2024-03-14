import time
import pytest
from gitbugactions.test_executor import TestExecutor
from gitbugactions.docker.client import DockerClient


@pytest.mark.skip(
    reason="Can potentially be flaky and should be used only to make sure the clean-up works."
)
def test_test_executor_cleanup():
    docker = DockerClient.getInstance()

    def get_test_container():
        for container in docker.containers.list(
            all=True, filters={"ancestor": "gitbugactions:latest"}
        ):
            if container.name == "test_test_executor_cleanup":
                return container
        return None

    docker = DockerClient.getInstance()

    test_container = get_test_container()
    if test_container is not None:
        test_container.stop()
        test_container.remove()

    container = docker.containers.create(
        "gitbugactions:latest", name="test_test_executor_cleanup"
    )
    container.start()
    container.stop()

    assert get_test_container() is not None
    TestExecutor._TestExecutor__schedule_cleanup("gitbugactions:latest")
    time.sleep(120)
    assert get_test_container() is None
