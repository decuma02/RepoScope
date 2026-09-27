/**
 * Formats internal clone paths into clean human-readable GitHub repository identifiers.
 *
 * e.g. "/app/data/clones/decuma02__RepoScope" => "github.com/decuma02/RepoScope"
 */
export function formatSourcePath(sourcePath: string, sourceType?: string): string {
  if (!sourcePath) return "";
  if (
    sourceType === "github" ||
    sourcePath.includes("clones/") ||
    sourcePath.includes("/clones/")
  ) {
    const parts = sourcePath.split(/[\/\\]/);
    const lastPart = parts[parts.length - 1] || "";
    if (lastPart.includes("__")) {
      const [owner, repo] = lastPart.split("__");
      return `github.com/${owner}/${repo}`;
    }
    if (lastPart) {
      return `github.com/${lastPart}`;
    }
  }
  return sourcePath;
}
