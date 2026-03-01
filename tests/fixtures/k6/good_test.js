import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    ramp_load: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      stages: [
        { duration: '2m', target: 50 },
        { duration: '5m', target: 50 },
        { duration: '1m', target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
  gracefulStop: '30s',
  gracefulRampDown: '30s',
};

const BASE_URL = __ENV.BASE_URL || 'https://staging.example.com';

export default function () {
  const res = http.get(`${BASE_URL}/api/users`, {
    tags: { name: 'get_users' },
    timeout: '10s',
  });

  check(res, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
  });

  if (res.status !== 200) {
    console.error(`Request failed with status: ${res.status}`);
  }

  sleep(1);
}
