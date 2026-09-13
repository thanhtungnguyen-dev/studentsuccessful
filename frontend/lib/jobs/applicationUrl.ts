/** One browser-side guard for the canonical Apply URL already selected by the API. */
export function safeApplicationUrl(value: string): string | null {
  if (
    [...value].some((character) => {
      const code = character.codePointAt(0) ?? 0;
      return code <= 0x20 || code === 0x7f || character === "\\";
    })
  ) return null;
  try {
    const url = new URL(value);
    return /^https?:\/\//i.test(value)
      && (url.protocol === "http:" || url.protocol === "https:")
      && Boolean(url.hostname)
      && !url.username
      && !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}
