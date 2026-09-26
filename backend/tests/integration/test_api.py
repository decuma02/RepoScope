import os
from fastapi.testclient import TestClient
from backend.app.main import app

def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["project"] == "RepoScope"

def test_repository_lifecycle_e2e():
    with TestClient(app) as client:
        # 1. Create Repository
        cwd = os.getcwd()
        create_res = client.post("/api/repositories", json={
            "name": "Test RepoScope",
            "sourceType": "local_path",
            "sourcePath": cwd
        })
        assert create_res.status_code == 201
        repo_data = create_res.json()
        repo_id = repo_data["id"]
        assert repo_data["name"] == "Test RepoScope"
        assert repo_data["status"] == "CREATED"

        # 2. Get Repository
        get_res = client.get(f"/api/repositories/{repo_id}")
        assert get_res.status_code == 200
        assert get_res.json()["id"] == repo_id

        # 3. Trigger Analysis
        analyze_res = client.post(f"/api/repositories/{repo_id}/analyze", json={"force": True})
        assert analyze_res.status_code == 202
        job_data = analyze_res.json()
        assert job_data["repositoryId"] == repo_id

        # 4. Poll Status
        status_res = client.get(f"/api/repositories/{repo_id}/status")
        assert status_res.status_code == 200

        # 5. Fetch Directory Tree
        tree_res = client.get(f"/api/repositories/{repo_id}/tree")
        assert tree_res.status_code == 200
        assert "tree" in tree_res.json()

        # 6. Fetch Components & Relationships List
        comps_res = client.get(f"/api/repositories/{repo_id}/components")
        assert comps_res.status_code == 200

        rels_res = client.get(f"/api/repositories/{repo_id}/relationships")
        assert rels_res.status_code == 200

        # 7. Run Relationship-Aware Search & Compare
        search_res = client.post(f"/api/repositories/{repo_id}/search", json={
            "query": "architecture boundary database",
            "limit": 5,
            "relationshipAware": True
        })
        assert search_res.status_code == 200

        compare_res = client.post(f"/api/repositories/{repo_id}/compare-retrieval", json={
            "query": "architecture boundary"
        })
        assert compare_res.status_code == 200

        # 8. Grounded AI Chat Query
        chat_res = client.post(f"/api/repositories/{repo_id}/chat", json={
            "question": "Where is boundary security implemented?"
        })
        assert chat_res.status_code == 200

        # 9. Focused Graph Query
        graph_res = client.get(f"/api/repositories/{repo_id}/graph")
        assert graph_res.status_code == 200

        # 10. Reset Repository
        reset_res = client.post(f"/api/repositories/{repo_id}/reset")
        assert reset_res.status_code == 200

def test_invalid_repository_error_format():
    with TestClient(app) as client:
        response = client.post("/api/repositories", json={
            "name": "Invalid Repo",
            "sourceType": "local_path",
            "sourcePath": "C:\\non_existent_path_9876543" if os.name == 'nt' else "/non_existent_path_9876543"
        })
        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "INVALID_REPOSITORY"
        assert "requestId" in data["error"]
