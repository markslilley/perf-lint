import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 10,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const res = http.get('http://192.168.1.100/api/users');  // Hardcoded IP!
  check(res, { 'status is 200': (r) => r.status === 200 });
  if (res.status !== 200) {
    console.error('Request failed');
  }
  sleep(1);
}
