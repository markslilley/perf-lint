/**
 * K6 Load Test — E-commerce checkout flow (BAD example)
 *
 * This script has several common quality problems that perf-lint will catch:
 *
 *   K6002 — Hardcoded IP address (should use BASE_URL env variable)
 *   K6001 — No think time between requests (VUs hammer the server flat out)
 *   K6003 — No response assertions (failures go undetected)
 *   K6004 — No thresholds (SLOs can't be enforced in CI)
 *   K6006 — Aggressive first stage (500 VUs in 5 seconds)
 *   K6005 — No error handling (script will silently swallow errors)
 *
 * Run:
 *   k6 run ecommerce_bad.js
 *
 * Then compare with ecommerce_good.js to see how to fix each issue.
 */

import http from 'k6/http';

export const options = {
  stages: [
    { duration: '5s',  target: 500 },  // K6006: Way too aggressive — 100 VUs/second!
    { duration: '5m',  target: 500 },
    { duration: '30s', target: 0   },
  ],
  // K6004: No thresholds — this test will always "pass" even if the app is on fire
};

export default function () {
  // K6002: Hardcoded IP — won't work against staging, prod, or any other environment
  const res = http.post('http://192.168.1.50/api/auth/login', JSON.stringify({
    email: 'testuser@example.com',
    password: 'password123',
  }), {
    headers: { 'Content-Type': 'application/json' },
  });

  // K6003: No assertions — if login returns 500, the script keeps going regardless

  // Pretend we have a token (we don't validate it)
  let token = 'fake-token';
  try {
    token = JSON.parse(res.body).token;
  } catch (e) {
    // K6005: Swallowing the error entirely — no logging, no counter, nothing
  }

  http.get('http://192.168.1.50/api/products');  // K6002: Another hardcoded IP
  // K6003: No assertion on the products response either

  http.post('http://192.168.1.50/api/cart/items', JSON.stringify({
    product_id: 'PRD-001',
    quantity: 1,
  }), {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
  });
  // K6003: No assertion on the cart response

  http.post('http://192.168.1.50/api/orders', JSON.stringify({
    payment_method: 'card_test',
  }), {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
  });
  // K6003: No assertion on the checkout response
  // K6001: No think time anywhere — VUs loop as fast as the network allows
}
