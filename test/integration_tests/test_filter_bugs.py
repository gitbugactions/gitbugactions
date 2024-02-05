import os, shutil
import json
import pytest
import tempfile
import uuid
from export_bugs import export_bugs
from filter_bugs import filter_bugs

export_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
res_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))


@pytest.fixture
def setup():
    if not os.path.exists(res_path):
        os.mkdir(res_path)
    export_bugs("test/resources/test_filter_bugs", export_path, n_workers=2)
    yield


@pytest.fixture
def teardown():
    yield
    shutil.rmtree(export_path)
    shutil.rmtree(res_path)


def test_filter_bugs(setup, teardown):
    filter_bugs("test/resources/test_filter_bugs", export_path, res_path, n_workers=2)

    flaky_path = os.path.join(res_path, "flaky.json")
    non_flaky_path = os.path.join(res_path, "non-flaky.json")
    assert os.path.exists(flaky_path)
    assert os.path.exists(non_flaky_path)

    with open(flaky_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["repository"] == "vanilladb/vanillacore"
        assert data["commit"] == "1b7b6cf1912f8a2c020e8cc759afaa675bb28014"

    with open(non_flaky_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["repository"] == "gitbugactions/gitbugactions-unittest-test-repo"
        assert data["commit"] == "d3d7a607e3a8abc330f8fd69f677284a9afaf650"
