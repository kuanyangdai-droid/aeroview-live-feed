export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatchWorkflow(env));
  },

  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Use POST to dispatch the workflow.\n", { status: 405 });
    }

    const auth = request.headers.get("authorization") || "";
    if (env.DISPATCH_WEBHOOK_TOKEN && auth !== `Bearer ${env.DISPATCH_WEBHOOK_TOKEN}`) {
      return new Response("Unauthorized\n", { status: 401 });
    }

    return dispatchWorkflow(env);
  },
};

async function dispatchWorkflow(env) {
  const owner = env.GITHUB_OWNER || "kuanyangdai-droid";
  const repo = env.GITHUB_REPO || "aeroview-live-feed";
  const workflow = env.GITHUB_WORKFLOW || "update-feed.yml";
  const ref = env.GITHUB_REF || "main";
  const token = env.GITHUB_TOKEN;

  if (!token) {
    return new Response("Missing GITHUB_TOKEN secret.\n", { status: 500 });
  }

  const response = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        "Accept": "application/vnd.github+json",
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
        "User-Agent": "aeroview-cloudflare-dispatcher",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref }),
    },
  );

  if (response.status === 204) {
    return new Response(`Dispatched ${owner}/${repo}/${workflow}@${ref}\n`, { status: 200 });
  }

  const body = await response.text();
  return new Response(`GitHub dispatch failed: HTTP ${response.status}\n${body}\n`, {
    status: response.status,
  });
}
