/** Read the current readable CSRF cookie immediately before a mutation. */
export function readCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  const value = document.cookie.split(";").map((part) => part.trim())
    .find((part) => part.startsWith("ss_csrf="))?.slice("ss_csrf=".length);
  if (!value) return null;
  try { return decodeURIComponent(value); } catch { return null; }
}
