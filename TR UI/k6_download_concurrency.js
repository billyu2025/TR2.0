import http from "k6/http";
import { check, sleep, fail } from "k6";
import { Trend, Rate, Counter } from "k6/metrics";

/**
 * ====== 配置 ======
 * 运行前可用环境变量覆盖：
 * BASE_URL, MODE, ORDER_NOS, USERS, DURATION, THINK_TIME
 * USER_LIST_JSON='[{"username":"u1","password":"p1"}, ...]'
 */

// 自定义指标
const loginDuration = new Trend("login_duration");
const createTaskDuration = new Trend("create_task_duration");
const pollDuration = new Trend("poll_status_duration");
const downloadDuration = new Trend("download_duration");

const taskCreateFailRate = new Rate("task_create_fail_rate");
const taskFinalFailRate = new Rate("task_final_fail_rate");
const downloadFailRate = new Rate("download_fail_rate");

const completedTasks = new Counter("completed_tasks");
const warningTasks = new Counter("warning_tasks");
const reloginCount = new Counter("relogin_count");

// 全局配置
const BASE_URL = (__ENV.BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const MODE = (__ENV.MODE || "order").toLowerCase(); // order | dd_no | date | all_stockist
const ORDER_NOS = (__ENV.ORDER_NOS || "134396,134321").split(",").map((x) => parseInt(x.trim(), 10)).filter(Boolean);
const THINK_TIME = Number(__ENV.THINK_TIME || "0.2"); // 秒

// 用户列表：建议并发测试时每个VU使用不同账号（单会话系统）
const USERS = __ENV.USER_LIST_JSON
  ? JSON.parse(__ENV.USER_LIST_JSON)
  : [
      { username: "test01", password: "test01" },
      { username: "test02", password: "test02" },
      { username: "test03", password: "test03" },
      { username: "test04", password: "test04" },
      { username: "test05", password: "test05" },
      { username: "test06", password: "test06" },
      { username: "test07", password: "test07" },
      { username: "test08", password: "test08" },
      { username: "test09", password: "test09" },
      { username: "test10", password: "test10" },
      { username: "test11", password: "test11" },
      { username: "test12", password: "test12" },
      { username: "test13", password: "test13" },
      { username: "test14", password: "test14" },
      { username: "test15", password: "test15" },
      { username: "test16", password: "test16" },
      { username: "test17", password: "test17" },
      { username: "test18", password: "test18" },
      { username: "test19", password: "test19" },
      { username: "test20", password: "test20" },
      { username: "test21", password: "test21" },
      { username: "test22", password: "test22" },
      { username: "test23", password: "test23" },
      { username: "test24", password: "test24" },
      { username: "test25", password: "test25" },
      { username: "test26", password: "test26" },
      { username: "test27", password: "test27" },
      { username: "test28", password: "test28" },
      { username: "test29", password: "test29" },
      { username: "test30", password: "test30" },
      { username: "test31", password: "test31" },
      { username: "test32", password: "test32" },
      { username: "test33", password: "test33" },
      { username: "test34", password: "test34" },
      { username: "test35", password: "test35" },
      { username: "test36", password: "test36" },
      { username: "test37", password: "test37" },
      { username: "test38", password: "test38" },
      { username: "test39", password: "test39" },
      { username: "test40", password: "test40" },
      { username: "test41", password: "test41" },
      { username: "test42", password: "test42" },
      { username: "test43", password: "test43" },
      { username: "test44", password: "test44" },
      { username: "test45", password: "test45" },
      { username: "test46", password: "test46" },
      { username: "test47", password: "test47" },
      { username: "test48", password: "test48" },
      { username: "test49", password: "test49" },
      { username: "test50", password: "test50" },
    ];

// k6 场景
export const options = {
  scenarios: {
    concurrent_downloads: {
      executor: "constant-vus",
      vus: Number(__ENV.USERS || "10"),
      duration: __ENV.DURATION || "5m",
      gracefulStop: "30s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    task_create_fail_rate: ["rate<0.05"],
    task_final_fail_rate: ["rate<0.10"],
    download_fail_rate: ["rate<0.10"],
    http_req_duration: ["p(95)<3000"],
  },
  insecureSkipTLSVerify: true,
};

// 根据 VU 轮转账号，避免同账号互踢影响基线
function pickUser() {
  const idx = (__VU - 1) % USERS.length;
  return USERS[idx];
}

// 统一请求头
function authHeaders(token) {
  return {
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    timeout: "120s",
  };
}

// 每个 VU 独立缓存 token（k6 中每个 VU 有自己的 JS 运行时）
let vuToken = null;

// 登录（根据你项目实际登录接口/字段调整）
function loginAndGetToken() {
  const user = pickUser();
  const payload = JSON.stringify({
    username: user.username,
    password: user.password,
  });

  // TODO: 如你系统登录接口不是 /api/auth/login，请改这里
  const res = http.post(`${BASE_URL}/api/auth/login`, payload, {
    headers: { "Content-Type": "application/json" },
    timeout: "30s",
    tags: { name: "login" },
  });

  loginDuration.add(res.timings.duration);

  const ok = check(res, {
    "login status is 200": (r) => r.status === 200,
    "login response has token": (r) => {
      try {
        const body = r.json();
        return !!(body.token || (body.data && body.data.token));
      } catch (_) {
        return false;
      }
    },
  });

  if (!ok) {
    fail(`Login failed. status=${res.status}, body=${res.body}`);
  }

  const body = res.json();
  return body.token || (body.data && body.data.token);
}

function getOrLoginToken() {
  if (vuToken) return vuToken;
  vuToken = loginAndGetToken();
  return vuToken;
}

function requestWithAuthRetry(method, url, body, tags = {}, extra = {}) {
  let token = getOrLoginToken();
  const baseParams = {
    ...authHeaders(token),
    tags,
    ...extra,
  };

  let res =
    method === "GET"
      ? http.get(url, baseParams)
      : http.post(url, body, baseParams);

  // 仅在 401 时重登并重试一次
  if (res.status === 401) {
    reloginCount.add(1);
    vuToken = loginAndGetToken();
    token = vuToken;
    const retryParams = {
      ...authHeaders(token),
      tags,
      ...extra,
    };
    res =
      method === "GET"
        ? http.get(url, retryParams)
        : http.post(url, body, retryParams);
  }

  return res;
}

function createDownloadTask(token) {
  let url = "";
  let payload = {};

  switch (MODE) {
    case "order":
      url = `${BASE_URL}/api/stockist-test/download-by-order-nos`;
      payload = { order_nos: ORDER_NOS };
      break;
    case "dd_no":
      url = `${BASE_URL}/api/stockist-test/download-by-order-nos-grouped-by-dd-no`;
      payload = { order_nos: ORDER_NOS };
      break;
    case "date":
      url = `${BASE_URL}/api/stockist-test/download-by-order-nos-grouped-by-date`;
      payload = { order_nos: ORDER_NOS };
      break;
    case "all_stockist":
      url = `${BASE_URL}/api/stockist-test/download-all-stockist-nos`;
      payload = { order_nos: ORDER_NOS };
      break;
    default:
      fail(`Unsupported MODE=${MODE}`);
  }

  const res = requestWithAuthRetry("POST", url, JSON.stringify(payload), {
    name: "create_download_task",
    mode: MODE,
  });

  createTaskDuration.add(res.timings.duration);

  let taskId = null;
  let success = false;
  try {
    const body = res.json();
    success = res.status === 200 && !!body.success && !!body.task_id;
    taskId = body.task_id;
  } catch (_) {}

  taskCreateFailRate.add(!success);

  if (!success) {
    fail(`Create task failed. status=${res.status}, body=${res.body}`);
  }

  return taskId;
}

function pollTaskUntilDone(token, taskId) {
  const maxPolls = Number(__ENV.MAX_POLLS || "600"); // 最多轮询次数
  const intervalSec = Number(__ENV.POLL_INTERVAL || "1"); // 每次间隔秒

  let hasWarning = false;
  let warningMessage = "";

  for (let i = 0; i < maxPolls; i++) {
    const res = requestWithAuthRetry(
      "GET",
      `${BASE_URL}/api/download/task-status/${taskId}`,
      null,
      { name: "poll_task_status" }
    );

    pollDuration.add(res.timings.duration);

    if (res.status !== 200) {
      sleep(intervalSec);
      continue;
    }

    let body;
    try {
      body = res.json();
    } catch (_) {
      sleep(intervalSec);
      continue;
    }

    if (!body.success) {
      sleep(intervalSec);
      continue;
    }

    if (body.status === "completed") {
      completedTasks.add(1);
      hasWarning = !!body.has_warning;
      warningMessage = body.warning_message || "";
      if (hasWarning) warningTasks.add(1);
      taskFinalFailRate.add(false);
      return { ok: true, hasWarning, warningMessage };
    }

    if (body.status === "failed") {
      taskFinalFailRate.add(true);
      fail(`Task failed. taskId=${taskId}, err=${body.error_message || body.message || "unknown"}`);
    }

    sleep(intervalSec);
  }

  taskFinalFailRate.add(true);
  fail(`Task polling timeout. taskId=${taskId}`);
}

function downloadZip(token, taskId) {
  const res = requestWithAuthRetry(
    "GET",
    `${BASE_URL}/api/download/download/${taskId}`,
    null,
    { name: "download_zip" },
    { responseType: "binary", timeout: "30m" }
  );

  downloadDuration.add(res.timings.duration);

  const ok = check(res, {
    "download status is 200": (r) => r.status === 200,
    "download content type is zip": (r) =>
      (r.headers["Content-Type"] || "").toLowerCase().includes("zip") ||
      (r.headers["Content-Type"] || "").toLowerCase().includes("application/octet-stream"),
    "download body not empty": (r) => r.body && r.body.byteLength > 0,
  });

  downloadFailRate.add(!ok);

  if (!ok) {
    fail(`Download failed. status=${res.status}, headers=${JSON.stringify(res.headers)}`);
  }
}

export default function () {
  const token = getOrLoginToken();
  sleep(THINK_TIME);

  const taskId = createDownloadTask(token);
  sleep(THINK_TIME);

  const result = pollTaskUntilDone(token, taskId);
  sleep(THINK_TIME);

  downloadZip(token, taskId);

  // 仅用于调试
  if (result.hasWarning) {
    console.log(`[VU ${__VU}] task=${taskId} has warning:\n${result.warningMessage}`);
  }
}