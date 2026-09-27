import pytest
from backend.app.services.github_service import GithubService
from backend.app.storage.boundary import RepositoryBoundaryError

def test_parse_github_url_valid_https():
    owner, repo = GithubService.parse_github_url("https://github.com/fastapi/fastapi")
    assert owner == "fastapi"
    assert repo == "fastapi"

def test_parse_github_url_valid_dot_git():
    owner, repo = GithubService.parse_github_url("https://github.com/pallets/flask.git")
    assert owner == "pallets"
    assert repo == "flask"

def test_parse_github_url_valid_shorthand():
    owner, repo = GithubService.parse_github_url("psf/requests")
    assert owner == "psf"
    assert repo == "requests"

def test_parse_github_url_invalid():
    with pytest.raises(RepositoryBoundaryError):
        GithubService.parse_github_url("invalid-url-string")
