export function normalizeInstagramRecipient(value) {
  const input = value.trim();
  const username = input.replace(/^@/, "");
  if (/^[a-zA-Z0-9._]{1,30}$/.test(username)) return `https://www.instagram.com/${username}/`;
  try {
    const url = new URL(/^https?:\/\//i.test(input) ? input : `https://${input}`);
    if (!["instagram.com", "www.instagram.com"].includes(url.hostname) || url.username || url.password || url.port) return "";
    const path = url.pathname.replace(/\/+$/, "");
    if (/^\/direct\/t\/\d+$/.test(path)) return `https://www.instagram.com${path}/`;
    if (/^\/[a-zA-Z0-9._]{1,30}$/.test(path) && !["direct", "accounts", "explore", "p", "reel", "reels", "stories"].includes(path.slice(1).toLowerCase())) {
      return `https://www.instagram.com${path}/`;
    }
  } catch { /* The field shows a validation message instead of accepting a bad link. */ }
  return "";
}
