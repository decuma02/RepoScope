import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getClient, isMockMode } from "../api";
import { ApiError } from "../api/client";
import { TopBar } from "../components/layout/TopBar";
import type { Repository } from "../types/reposcope";

/**
 * HomePage — Landing page and repository registration hub.
 *
 * Responsibilities:
 *   - Displays the hero banner and RepoScope branding.
 *   - Provides a form to register a new repository (local path or GitHub URL).
 *   - Supports toggling between "local_path" and "github" source types;
 *     switching auto-fills a sensible default repository name.
 *   - On submit: calls ``createRepository`` → triggers ``analyze`` →
 *     navigates to ``/workspace/:id``.
 *   - Lists the 5 most-recently registered workspaces from the API
 *     (auto-refreshes on mock mode toggle).
 *   - Renders in mock mode when ``?mock=1`` is in the URL, showing fixture data
 *     without a running backend.
 */
export function HomePage() {
  const navigate = useNavigate();
  const mock = isMockMode();
  const [repos, setRepos] = useState<Repository[]>([]);
  const [sourceType, setSourceType] = useState<"local_path" | "github">("local_path");
  const [name, setName] = useState("My Repository");
  const [sourcePath, setSourcePath] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
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

  /**
   * Form submit handler.
   *
   * Builds the correct request payload for the selected source type, posts it
   * to the backend, fires analysis immediately, then navigates to the workspace.
   * Displays an inline error banner if any step fails.
   */
  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const payload =
        sourceType === "github"
          ? { name: name || "GitHub Repository", sourceType: "github", githubUrl, sourcePath: "" }
          : { name: name || "Local Repository", sourceType: "local_path", sourcePath };

      const repo = await getClient().createRepository(payload);
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
            Register a local directory path or clone a public GitHub repository, run one-shot analysis, explore files, inspect the focused relationship graph, and chat with answers that cite real source ranges.
          </p>
        </section>
        <div className="home-grid">
          <div className="card">
            <h3>Register a repository</h3>
            
            {/* Source Type Toggle */}
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              <button
                type="button"
                className={`btn ${sourceType === "local_path" ? "" : "secondary"}`}
                style={{ flex: 1, fontSize: 12 }}
                onClick={() => {
                  setSourceType("local_path");
                  if (name === "GitHub Repository") setName("Local Repository");
                }}
              >
                💻 Local Directory
              </button>
              <button
                type="button"
                className={`btn ${sourceType === "github" ? "" : "secondary"}`}
                style={{ flex: 1, fontSize: 12 }}
                onClick={() => {
                  setSourceType("github");
                  if (name === "Local Repository") setName("GitHub Repository");
                }}
              >
                🐙 GitHub Repository
              </button>
            </div>

            <form onSubmit={onSubmit}>
              <div className="field">
                <label htmlFor="repo-name">Repository Name</label>
                <input id="repo-name" value={name} onChange={(event) => setName(event.target.value)} required />
              </div>

              {sourceType === "local_path" ? (
                <div className="field">
                  <label htmlFor="repo-path">Absolute Local Path</label>
                  <input
                    id="repo-path"
                    value={sourcePath}
                    onChange={(event) => setSourcePath(event.target.value)}
                    placeholder="e.g. D:\git\my-project"
                    required
                  />
                </div>
              ) : (
                <div className="field">
                  <label htmlFor="repo-url">Public GitHub Repository URL</label>
                  <input
                    id="repo-url"
                    value={githubUrl}
                    onChange={(event) => {
                      const val = event.target.value;
                      setGithubUrl(val);
                      // Auto infer name from URL if name is generic
                      if (val && (name === "GitHub Repository" || name === "Local Repository" || !name)) {
                        const parts = val.replace(/\/$/, "").split("/");
                        const repoName = parts[parts.length - 1]?.replace(/\.git$/, "");
                        if (repoName) setName(repoName);
                      }
                    }}
                    placeholder="https://github.com/fastapi/fastapi"
                    required
                  />
                </div>
              )}

              {error ? <p className="error">{error}</p> : null}

              <button className="btn" disabled={busy} type="submit" style={{ width: "100%", marginTop: 8 }}>
                {busy ? (sourceType === "github" ? "Cloning & Analyzing…" : "Registering…") : "Register & Analyze"}
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
              {repos.slice(0, 5).map((repo) => (
                <Link className="repo-row" key={repo.id} to={`/workspace/${repo.id}`}>
                  <div>
                    <strong>{repo.name}</strong>
                    <div className="meta">{repo.sourcePath}</div>
                  </div>
                  <span className={`badge ${repo.status}`}>{repo.status}</span>
                </Link>
              ))}
              {!loading && repos.length > 5 ? (
                <p className="meta" style={{ marginTop: 8 }}>
                  Showing 5 most recent of {repos.length} workspaces
                </p>
              ) : null}
              {!loading && repos.length === 0 ? <p className="meta">No repositories yet.</p> : null}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
