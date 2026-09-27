import { api } from "./client";
import { mockApi } from "./mock";

const MOCK_KEY = "reposcope.mock";

export function isMockMode(): boolean {
  if (import.meta.env.VITE_USE_MOCK === "true") return true;
  const params = new URLSearchParams(window.location.search);
  if (params.get("mock") === "1") {
    sessionStorage.setItem(MOCK_KEY, "1");
    return true;
  }
  if (params.get("mock") === "0") {
    sessionStorage.removeItem(MOCK_KEY);
    return false;
  }
  return sessionStorage.getItem(MOCK_KEY) === "1";
}

export function getClient() {
  return isMockMode() ? mockApi : api;
}
