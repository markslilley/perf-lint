/**
 * K6 Load Test — REST API spike test (GOOD example)
 *
 * Tests how a REST API handles a sudden burst of traffic, then recovers.
 * Demonstrates: spike test pattern, per-endpoint thresholds, groups, tags.
 *
 * Run:
 *   BASE_URL=https://api.staging.example.com k6 run api_spike_test.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '1m',  target: 10  },  // Baseline
    { duration: '30s', target: 10  },  // Hold baseline
    { duration: '30s', target: 200 },  // Spike!
    { duration: '1m',  target: 200 },  // Hold spike
    { duration: '30s', target: 10  },  // Recover
    { duration: '1m',  target: 10  },  // Confirm recovery
    { duration: '30s', target: 0   },  // Ramp-down
  ],
  thresholds: {
    http_req_duration: ['p(95)<800'],
    http_req_failed:   ['rate<0.05'],  // Allow higher error rate during spike
    errors:            ['rate<0.05'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'https://api.staging.example.com';

const ENDPOINTS = [
  '/api/v1/users',
  '/api/v1/products',
  '/api/v1/orders',
  '/api/v1/health',
];

export default function () {
  group('Read-only API calls', () => {
    for (const endpoint of ENDPOINTS) {
      const res = http.get(`${BASE_URL}${endpoint}`, {
        tags: { endpoint },
      });

      const ok = check(res, {
        [`${endpoint} status 200`]: (r) => r.status === 200,
        [`${endpoint} < 800ms`]:    (r) => r.timings.duration < 800,
      });

      errorRate.add(!ok);

      if (!ok) {
        console.warn(`${endpoint} failed: HTTP ${res.status}`);
      }
    }
  });

  sleep(1);  // 1 second think time between iterations
}
