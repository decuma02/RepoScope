import { Link } from "react-router-dom";
import type { Repository } from "../../types/reposcope";
import { isMockMode } from "../../api";

export function TopBar({ repo }: { repo?: Repository }) {
  const mock = isMockMode();
  return (
    <>
      {mock ? (
        <div className="mock-banner">
          Fixture mode — using bundled JSON fixtures.{" "}
          <a href="?mock=0" style={{ color: "white", fontWeight: "bold", textDecoration: "underline", marginLeft: 6 }}>
            Click here to switch to Live API (?mock=0)
          </a>
        </div>
      ) : null}
      <header className="topbar">
        <Link className="brand" to="/">
          <img src="/logo-icon.png" alt="RepoScope" className="brand-logo-img" />
          <div>
            <h1>RepoScope</h1>
            <span>Repository intelligence</span>
          </div>
        </Link>
        {repo ? (
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div>
              <strong>{repo.name}</strong>
              <div className="meta">{repo.sourcePath}</div>
            </div>
            <span className={`badge ${repo.status}`}>{repo.status}</span>
          </div>
        ) : (
          <span className="badge">IBM Bob 2.0</span>
        )}
      </header>
    </>
  );
}
