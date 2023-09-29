import os
import pytest
from crawlergpt.limit import LimitFolderSize

limit_reached = False
test_dir_path = "test/resources/test_limit_folder_size/test_dir"


@pytest.fixture
def teardown():
    yield
    if os.path.exists(test_dir_path):
        os.rmdir(test_dir_path)


def trigger_limit_reached():
    global limit_reached
    limit_reached = True


def test_limit_folder_size(teardown):
    limit = LimitFolderSize(
        "test/resources/test_limit_folder_size", 4132, trigger_limit_reached
    )
    os.mkdir(test_dir_path)
    limit.observer.join()
    assert limit_reached == True
