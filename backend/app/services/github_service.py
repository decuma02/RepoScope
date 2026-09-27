import os
import re
import shutil
import subprocess
import zipfile
import urllib.request
from pathlib import Path
from backend.app.storage.boundary import RepositoryBoundaryError

class GithubService:
    """
    Handles cloning or downloading public GitHub repositories into a local storage path.
    """

    @staticmethod
    def parse_github_url(github_url: str) -> tuple[str, str]:
        """
        Parses owner and repo name from various GitHub URL formats:
        - https://github.com/owner/repo
        - https://github.com/owner/repo.git
        - git@github.com:owner/repo.git
        - owner/repo
        """
        clean_url = github_url.strip()
        if not clean_url:
            raise RepositoryBoundaryError("GitHub URL cannot be empty.")

        # Pattern for standard HTTPS or SSH GitHub URLs
        pattern = r"(?:https?://github\.com/|git@github\.com:|^)([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+?)(?:\.git|/)?$"
        match = re.match(pattern, clean_url)
        if not match:
            raise RepositoryBoundaryError(f"Invalid GitHub repository URL format: '{github_url}'")

        owner, repo = match.group(1), match.group(2)
        return owner, repo

    @classmethod
    def clone_or_fetch(cls, github_url: str, base_dir: str = "data/clones") -> str:
        """
        Clones or fetches the GitHub repository and returns the local root directory path.
        """
        owner, repo = cls.parse_github_url(github_url)
        repo_slug = f"{owner}__{repo}"

        dest_dir = Path(base_dir).resolve() / repo_slug
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Check if already cloned and populated
        if any(dest_dir.iterdir()):
            return str(dest_dir)

        full_https_url = f"https://github.com/{owner}/{repo}.git"

        # Strategy 1: Try fast shallow git clone
        try:
            res = subprocess.run(
                ["git", "clone", "--depth", "1", full_https_url, str(dest_dir)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
            )
            if res.returncode == 0 and any(dest_dir.iterdir()):
                return str(dest_dir)
        except Exception:
            # Fall back to zip download if git command is missing/fails
            pass

        # Strategy 2: Download archive zip from GitHub main/master branches
        for branch in ["main", "master"]:
            zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
            zip_path = dest_dir / "repo_archive.zip"
            try:
                urllib.request.urlretrieve(zip_url, zip_path)
                if zip_path.exists() and zip_path.stat().st_size > 0:
                    with zipfile.ZipFile(zip_path, "r") as zip_ref:
                        zip_ref.extractall(dest_dir)
                    zip_path.unlink()

                    # Move extracted subfolder contents to dest_dir if nested
                    extracted_subdirs = [p for p in dest_dir.iterdir() if p.is_dir()]
                    if len(extracted_subdirs) == 1 and not any(p for p in dest_dir.iterdir() if p.is_file()):
                        nested_dir = extracted_subdirs[0]
                        for item in nested_dir.iterdir():
                            shutil.move(str(item), str(dest_dir / item.name))
                        nested_dir.rmdir()

                    return str(dest_dir)
            except Exception:
                if zip_path.exists():
                    zip_path.unlink()

        raise RepositoryBoundaryError(
            f"Failed to clone or download GitHub repository '{github_url}'. Check URL visibility and network connection."
        )
