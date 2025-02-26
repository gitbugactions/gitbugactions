import json
import os
import shutil
import tempfile
import uuid

import pytest

from export_bugs import export_bugs
from filter_bugs import filter_bugs

export_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
res_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
base_image = "ghcr.io/catthehacker/ubuntu:runner-latest"


@pytest.fixture
def setup_flaky():
    if not os.path.exists(res_path):
        os.mkdir(res_path)
    export_bugs("test/resources/test_filter_bugs/flaky", export_path)
    yield


@pytest.fixture
def setup_non_flaky():
    if not os.path.exists(res_path):
        os.mkdir(res_path)
    export_bugs(
        "test/resources/test_filter_bugs/non_flaky", export_path, base_image=base_image
    )
    yield


@pytest.fixture
def teardown():
    yield
    shutil.rmtree(export_path)
    shutil.rmtree(res_path)


@pytest.mark.skip(reason="Skipped due to unreproducible results")
def test_filter_flaky_bugs(setup_flaky, teardown):
    filter_bugs(
        "test/resources/test_filter_bugs/flaky",
        export_path,
        res_path,
        n_workers=2,
        base_image=base_image,
    )

    flaky_path = os.path.join(res_path, "flaky.json")
    assert os.path.exists(flaky_path)

    with open(flaky_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["repository"] == "vanilladb/vanillacore"
        assert data["commit"] == "1b7b6cf1912f8a2c020e8cc759afaa675bb28014"


def test_filter_non_flaky_bugs(setup_non_flaky, teardown):
    filter_bugs(
        "test/resources/test_filter_bugs/non_flaky",
        export_path,
        res_path,
        n_workers=2,
        n_executions=2,
        base_image=base_image,
    )

    non_flaky_path = os.path.join(res_path, "non-flaky.json")
    assert os.path.exists(non_flaky_path)

    with open(non_flaky_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["repository"] == "gitbugactions/gitbugactions-unittest-test-repo"
        assert data["commit"] == "d3d7a607e3a8abc330f8fd69f677284a9afaf650"
