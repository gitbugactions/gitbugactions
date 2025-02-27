import os
import pytest
import shutil
import tempfile
from organize_bugs import organize_bugs


@pytest.fixture
def setup():
    global output_dir
    output_dir = tempfile.mkdtemp(prefix="organized_bugs_")
    yield


@pytest.fixture
def teardown():
    yield
    shutil.rmtree(output_dir)


def test_organize_bugs(setup, teardown):
    collect_bugs_dir = "test/resources/test_organize_bugs/collect_bugs_javascript"
    export_bugs_dir = "test/resources/test_organize_bugs/export_bugs_javascript"
    filter_bugs_dir = "test/resources/test_organize_bugs/filter_bugs_javascript"

    organize_bugs(collect_bugs_dir, export_bugs_dir, filter_bugs_dir, output_dir)

    # Check if the output directory is created
    assert os.path.exists(output_dir)

    # Check if the bugs directory is created
    bugs_dir = os.path.join(output_dir, "bugs")
    assert os.path.exists(bugs_dir)

    # Check if the JSON files for the repositories are created with lowercase names
    assert os.path.exists(
        os.path.join(bugs_dir, "zazuko-shacl-playground".lower() + ".json")
    )
    assert os.path.exists(
        os.path.join(bugs_dir, "nucleoidai-react-event".lower() + ".json")
    )

    # Check if the export directories for the commits are copied with lowercase names
    assert os.path.exists(
        os.path.join(
            output_dir,
            "zazuko-shacl-playground".lower(),
            "e62b5cb566359b6c4b4a06a8d83b9400c3c9eecb".lower(),
        )
    )
    assert os.path.exists(
        os.path.join(
            output_dir,
            "nucleoidai-react-event".lower(),
            "5fb2c12707c8d5b7b56cb333edde673dd7003a93".lower(),
        )
    )

    # Add test for NON_CODE bugs being ignored - if we add one in the test resources
    # The existing test already implicitly tests this if there are no NON_CODE bugs in the test data
