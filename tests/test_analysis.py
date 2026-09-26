from app.analysis.structure import StructureExtractor
from app.analysis.relationships import RelationshipExtractor

def test_structure_extractor_python():
    content = """
class AuthController:
    def login(self, username, password):
        return True

def validate_token(token):
    pass
"""
    components = StructureExtractor.extract_components("file_1", "repo_1", "auth.py", content)
    assert len(components) == 3
    names = [c["name"] for c in components]
    assert "AuthController" in names
    assert "login" in names
    assert "validate_token" in names

def test_relationship_extractor_python_imports():
    files_map = {
        "file_a": {"relative_path": "app/auth.py"},
        "file_b": {"relative_path": "app/user.py"}
    }
    components_by_file = {
        "file_a": [],
        "file_b": [{"id": "comp_1", "name": "user_service"}]
    }
    file_contents = {
        "file_a": "from app import user\nimport os\n",
        "file_b": "def user_service(): pass\n"
    }
    rels = RelationshipExtractor.extract_relationships("repo_1", files_map, components_by_file, file_contents)
    assert len(rels) >= 1
    rel_types = [r["type"].value if hasattr(r["type"], "value") else r["type"] for r in rels]
    assert "IMPORTS" in rel_types
