const CHALLENGE_HEADERS = {
  "www-authenticate": 'Basic realm="100 Lives", charset="UTF-8"',
  "cache-control": "no-store",
};

function equalHex(a, b) {
  if (a.length !== b.length) return false;
  let difference = 0;
  for (let i = 0; i < a.length; i++) difference |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return difference === 0;
}

export async function authorize(request, passwordHash) {
  if (!/^[a-f0-9]{64}$/.test(passwordHash || "")) {
    return new Response("访问密码尚未配置", { status: 503, headers: { "cache-control": "no-store" } });
  }

  const authorization = request.headers.get("authorization") || "";
  if (authorization.startsWith("Basic ")) {
    try {
      const decoded = atob(authorization.slice(6));
      const colon = decoded.indexOf(":");
      if (colon !== -1 && decoded.slice(0, colon) === "visitor") {
        const password = decoded.slice(colon + 1);
        const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(password));
        const hex = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
        if (equalHex(hex, passwordHash)) return null;
      }
    } catch {
      // Malformed credentials receive the same challenge as a wrong password.
    }
  }

  return new Response("需要访问密码", { status: 401, headers: CHALLENGE_HEADERS });
}
