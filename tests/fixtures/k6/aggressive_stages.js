import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '5s', target: 500 },  // Way too aggressive!
    { duration: '5m', target: 500 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const res = http.get('https://example.com/api/users');
  check(res, { 'status is 200': (r) => r.status === 200 });
  if (res.status !== 200) {
    console.error('Request failed');
  }
  sleep(1);
}
