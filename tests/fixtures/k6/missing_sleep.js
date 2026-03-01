import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 10,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<500'],
  },
};

export default function () {
  const res = http.get('https://example.com/api/users');
  check(res, {
    'status is 200': (r) => r.status === 200,
  });
  // No think time added here — unrealistic!
}
