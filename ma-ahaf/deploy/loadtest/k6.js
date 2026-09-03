// Load test for POST /v1/generate.
//
//   k6 run -e BASE=http://localhost:8000 -e API_KEY=dev-key deploy/loadtest/k6.js
//
// Stages ramp to 20 concurrent virtual users. /v1/generate is LLM-bound, so
// expect p95 in the multi-second range with real providers — the thresholds
// below are a starting SLO, tune to your model + hardware.

import http from "k6/http";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";

const genLatency = new Trend("generate_latency_ms", true);

export const options = {
  scenarios: {
    ramp: {
      executor: "ramping-vus",
      startVUs: 1,
      stages: [
        { duration: "1m", target: 5 },
        { duration: "3m", target: 20 },
        { duration: "1m", target: 20 },
        { duration: "1m", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.02"],
    "generate_latency_ms": ["p(95)<20000"],
  },
};

const BASE = __ENV.BASE || "http://localhost:8000";
const API_KEY = __ENV.API_KEY || "dev-key";

const PROMPTS = [
  "What is the ACME refund policy for annual plans?",
  "Compare the ACME Standard and Enterprise support tiers.",
  "What encryption does ACME use for data at rest?",
  "Write a two-line poem about a raindrop returning to the sea.",
  "What is the safe daily dose of ibuprofen for a 6-year-old child?",
];

export default function () {
  const prompt = PROMPTS[Math.floor(Math.random() * PROMPTS.length)];
  const res = http.post(
    `${BASE}/v1/generate`,
    JSON.stringify({ prompt }),
    { headers: { "Content-Type": "application/json", "x-api-key": API_KEY }, timeout: "60s" }
  );
  genLatency.add(res.timings.duration);
  check(res, {
    "status 200": (r) => r.status === 200,
    "has trace_id": (r) => r.json("trace_id") !== undefined,
    "has action": (r) => ["answer", "qualify", "abstain", "escalate"].includes(r.json("action")),
  });
  sleep(Math.random() * 2);
}
