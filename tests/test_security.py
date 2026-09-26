import os
import pytest
from app.security.repository_boundary import RepositoryBoundaryValidator, RepositoryBoundaryError
from app.analysis.ignore_rules import IgnoreRuleEvaluator

def test_boundary_validation_success():
    cwd = os.getcwd()
    validated = RepositoryBoundaryValidator.validate_repository_root(cwd)
    assert os.path.isabs(validated)

def test_boundary_validation_invalid_path():
    with pytest.raises(RepositoryBoundaryError):
        RepositoryBoundaryValidator.validate_repository_root("/non_existent_directory_123456")

def test_path_traversal_detection():
    root = os.getcwd()
    traversal_path = "../outside.txt"

    with pytest.raises(RepositoryBoundaryError):
        RepositoryBoundaryValidator.resolve_safe_path(root, traversal_path)

def test_ignore_rules():
    assert IgnoreRuleEvaluator.should_ignore_dir(".git") is True
    assert IgnoreRuleEvaluator.should_ignore_dir("node_modules") is True
    assert IgnoreRuleEvaluator.is_secret_file(".env") is True
    assert IgnoreRuleEvaluator.is_binary_file("image.png") is True
