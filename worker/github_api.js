const GITHUB_API = "https://api.github.com";

function githubHeaders(env) {
  return {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: "application/vnd.github+json",
    "Content-Type": "application/json",
    "User-Agent": "task-dingtalk-scheduler-worker",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

function assertGitHubConfig(env) {
  const required = ["GITHUB_TOKEN", "GITHUB_OWNER", "GITHUB_REPO", "GITHUB_BRANCH"];
  const missing = required.filter((key) => !env[key]);
  if (missing.length) {
    throw new Error(`Missing Cloudflare variable(s): ${missing.join(", ")}`);
  }
}

export async function getFileSHA(env, path) {
  assertGitHubConfig(env);
  const url = `${GITHUB_API}/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/contents/${encodeURIComponentPath(path)}?ref=${encodeURIComponent(env.GITHUB_BRANCH)}`;
  const response = await fetch(url, { headers: githubHeaders(env) });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`GitHub get file failed: ${response.status} ${await response.text()}`);
  }
  const payload = await response.json();
  return payload.sha || null;
}

export async function uploadFile(env, path, contentBase64, message) {
  assertGitHubConfig(env);
  const sha = await getFileSHA(env, path);
  return commitFile(env, path, contentBase64, message, sha);
}

export async function commitFile(env, path, contentBase64, message, sha = null) {
  assertGitHubConfig(env);
  const body = {
    message,
    content: contentBase64,
    branch: env.GITHUB_BRANCH,
  };
  if (sha) {
    body.sha = sha;
  }

  const url = `${GITHUB_API}/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/contents/${encodeURIComponentPath(path)}`;
  const response = await fetch(url, {
    method: "PUT",
    headers: githubHeaders(env),
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`GitHub commit failed: ${response.status} ${await response.text()}`);
  }
  return response.json();
}

export async function dispatchWorkflow(env, workflowFile = "dingtalk.yml", inputs = {}) {
  assertGitHubConfig(env);
  const url = `${GITHUB_API}/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${encodeURIComponent(workflowFile)}/dispatches`;
  const response = await fetch(url, {
    method: "POST",
    headers: githubHeaders(env),
    body: JSON.stringify({ ref: env.GITHUB_BRANCH, inputs }),
  });
  if (!response.ok) {
    throw new Error(`GitHub workflow dispatch failed: ${response.status} ${await response.text()}`);
  }
}

export async function getLatestWorkflowRun(env, workflowFile = "dingtalk.yml") {
  assertGitHubConfig(env);
  const url = `${GITHUB_API}/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${encodeURIComponent(workflowFile)}/runs?branch=${encodeURIComponent(env.GITHUB_BRANCH)}&per_page=1`;
  const response = await fetch(url, { headers: githubHeaders(env) });
  if (!response.ok) {
    throw new Error(`GitHub workflow status failed: ${response.status} ${await response.text()}`);
  }
  const payload = await response.json();
  return payload.workflow_runs?.[0] || null;
}

function encodeURIComponentPath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}
