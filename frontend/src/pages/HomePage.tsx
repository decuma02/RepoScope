import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getClient, isMockMode } from "../api";
import { ApiError } from "../api/client";
import { TopBar } from "../components/layout/TopBar";
import type { Repository } from "../types/reposcope";

export function HomePage() {
  const navigate = useNavigate();
  const mock = isMockMode();
  const [repos, setRepos] = useState<Repository[]>([]);
  const [name, setName] = useState("Local repository");
  const [sourcePath, setSourcePath] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getClient()
      .listRepositories()
      .then((payload) => setRepos(payload.repositories))
      .catch((err: unknown) => {
        setError(
          err instanceof ApiError
            ? err.message
            : "Backend is not reachable. Start FastAPI on :8000, or open /?mock=1.",
        );
      })
      .finally(() => setLoading(false));
  }, [mock]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const repo = await getClient().createRepository({ name, sourcePath });
      try {
        await getClient().analyze(repo.id, false);
      } catch {
        // workspace still works; analysis can be retried there
      }
      navigate(`/workspace/${repo.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not register repository.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <TopBar />
      <main className="home">
        <section className="hero">
          <img src="/logo-full.png" alt="RepoScope Logo" className="hero-logo-img" />
          <h2>See the repository, then ask it grounded questions.</h2>
          <p>
            Register a local path, run one-shot analysis, explore files, inspect the focused relationship graph, and
            chat with answers that cite real source ranges.
          </p>
        </section>
        <div className="home-grid">
          <div className="card">
            <h3>Register a repository</h3>
            <form onSubmit={onSubmit}>
              <div className="field">
                <label htmlFor="repo-name">Name</label>
                <input id="repo-name" value={name} onChange={(event) => setName(event.target.value)} required />
              </div>
              <div className="field">
                <label htmlFor="repo-path">Absolute local path</label>
                <input
                  id="repo-path"
                  value={sourcePath}
                  onChange={(event) => setSourcePath(event.target.value)}
                  placeholder="D:\\git\\akhil_repo_list\\work\\RepoScope"
                  required
                />
              </div>
              {error ? <p className="error">{error}</p> : null}
              <button className="btn" disabled={busy} type="submit">
                {busy ? "Registering…" : "Register & analyze"}
              </button>
              {!mock ? (
                <p className="meta" style={{ marginTop: 12 }}>
                  Need a walkthrough without the API?{" "}
                  <Link to="/?mock=1">Open fixture mode</Link>
                </p>
              ) : null}
            </form>
          </div>
          <div className="card">
            <h3>Workspaces</h3>
            {loading ? <p className="meta">Loading repositories…</p> : null}
            <div className="repo-list">
              {repos.map((repo) => (
                <Link className="repo-row" key={repo.id} to={`/workspace/${repo.id}`}>
                  <div>
                    <strong>{repo.name}</strong>
                    <div className="meta">{repo.sourcePath}</div>
                  </div>
                  <span className={`badge ${repo.status}`}>{repo.status}</span>
                </Link>
              ))}
              {!loading && repos.length === 0 ? <p className="meta">No repositories yet.</p> : null}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
