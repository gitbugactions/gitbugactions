from collect_bugs import PatchCollector
from unittest.mock import Mock


def test_is_bug_fix():
    repo = Mock()
    repo.language.return_value = "java"
    collector = PatchCollector(repo)

    commit = Mock()
    commit.message = "fixing bug"
    assert collector._PatchCollector__is_bug_fix(commit)
    commit.message = "bug"
    assert not collector._PatchCollector__is_bug_fix(commit)
    commit.message = "Test test. Fixes bug"
    assert collector._PatchCollector__is_bug_fix(commit)
    commit.message = "Test test. Prefix"
    assert not collector._PatchCollector__is_bug_fix(commit)
    commit.message = "Test test. Small fix"
    assert collector._PatchCollector__is_bug_fix(commit)
