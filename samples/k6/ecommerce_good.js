/**
 * K6 Load Test — E-commerce checkout flow (GOOD example)
 *
 * Demonstrates best practices:
 *   - Parameterised base URL via __ENV
 *   - Thresholds that enforce SLOs
 *   - Gradual ramp-up stages
 *   - check() on every response
 *   - sleep() between requests (think time)
 *   - Error handling and logging
 *
 * Run:
 *   BASE_URL=https://staging.example.com k6 run ecommerce_good.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// ── Custom metrics ────────────────────────────────────────────────────────────
const checkoutErrors = new Counter('checkout_errors');
const checkoutDuration = new Trend('checkout_duration');
const addToCartRate = new Rate('add_to_cart_success_rate');

// ── Options ───────────────────────────────────────────────────────────────────
export const options = {
  stages: [
    { duration: '2m',  target: 20  },  // Warm-up: ramp to 20 VUs over 2 minutes
    { duration: '5m',  target: 50  },  // Ramp-up: increase to 50 VUs
    { duration: '10m', target: 50  },  // Steady state: hold at 50 VUs
    { duration: '2m',  target: 0   },  // Ramp-down: graceful teardown
  ],
  thresholds: {
    // 95% of requests must complete within 500ms
    http_req_duration:        ['p(95)<500', 'p(99)<1500'],
    // Error rate must stay below 1%
    http_req_failed:          ['rate<0.01'],
    // Custom metric: checkout must complete within 2 seconds
    checkout_duration:        ['p(95)<2000'],
    // Cart success rate must be above 99%
    add_to_cart_success_rate: ['rate>0.99'],
  },
};

// ── Configuration ─────────────────────────────────────────────────────────────
const BASE_URL = __ENV.BASE_URL || 'https://staging.example.com';

// Simulated product catalogue — in a real test, load from a CSV feeder
const PRODUCTS = [
  { id: 'PRD-001', name: 'Wireless Headphones', price: 79.99 },
  { id: 'PRD-002', name: 'USB-C Hub',            price: 49.99 },
  { id: 'PRD-003', name: 'Laptop Stand',          price: 34.99 },
];

// Simulated user accounts — in a real test, load from a CSV feeder
const USERS = [
  { email: 'alice@example.com',   password: 'testpass123' },
  { email: 'bob@example.com',     password: 'testpass456' },
  { email: 'charlie@example.com', password: 'testpass789' },
];

// ── Helpers ───────────────────────────────────────────────────────────────────
function randomItem(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function getHeaders(token) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

// ── Main scenario ─────────────────────────────────────────────────────────────
export default function () {
  const user = randomItem(USERS);
  const product = randomItem(PRODUCTS);
  let token = null;

  // 1. Browse the homepage
  group('Homepage', () => {
    const res = http.get(`${BASE_URL}/`);
    check(res, {
      'homepage status 200':          (r) => r.status === 200,
      'homepage loads within 1s':     (r) => r.timings.duration < 1000,
      'homepage has product listing': (r) => r.body && r.body.includes('products'),
    });
    sleep(2);  // User browses for ~2 seconds
  });

  // 2. Browse the product catalogue
  group('Product catalogue', () => {
    const res = http.get(`${BASE_URL}/api/products?limit=20`);
    check(res, {
      'catalogue status 200':  (r) => r.status === 200,
      'catalogue has items':   (r) => {
        try {
          const body = JSON.parse(r.body);
          return Array.isArray(body.items) && body.items.length > 0;
        } catch {
          return false;
        }
      },
    });
    sleep(3);  // User browses for ~3 seconds
  });

  // 3. View a specific product
  group('Product detail', () => {
    const res = http.get(`${BASE_URL}/api/products/${product.id}`);
    check(res, {
      'product detail status 200': (r) => r.status === 200,
      'product has price':         (r) => r.body && r.body.includes('price'),
    });
    sleep(5);  // User reads the product page for ~5 seconds
  });

  // 4. Log in
  group('Login', () => {
    const res = http.post(
      `${BASE_URL}/api/auth/login`,
      JSON.stringify({ email: user.email, password: user.password }),
      { headers: getHeaders() },
    );

    const loginOk = check(res, {
      'login status 200':     (r) => r.status === 200,
      'login returns token':  (r) => {
        try {
          return !!JSON.parse(r.body).token;
        } catch {
          return false;
        }
      },
    });

    if (loginOk) {
      try {
        token = JSON.parse(res.body).token;
      } catch {
        console.error(`Failed to parse login response: ${res.body}`);
      }
    } else {
      console.warn(`Login failed for ${user.email}: HTTP ${res.status}`);
    }

    sleep(1);
  });

  if (!token) {
    console.error('No auth token — skipping cart and checkout');
    return;
  }

  // 5. Add item to cart
  group('Add to cart', () => {
    const startTime = Date.now();
    const res = http.post(
      `${BASE_URL}/api/cart/items`,
      JSON.stringify({ product_id: product.id, quantity: 1 }),
      { headers: getHeaders(token) },
    );

    const success = check(res, {
      'add to cart status 201': (r) => r.status === 201,
      'cart item confirmed':    (r) => r.body && r.body.includes(product.id),
    });

    addToCartRate.add(success);
    if (!success) {
      console.error(`Add to cart failed: HTTP ${res.status}`);
    }

    sleep(2);
  });

  // 6. Checkout
  group('Checkout', () => {
    const startTime = Date.now();
    const res = http.post(
      `${BASE_URL}/api/orders`,
      JSON.stringify({
        payment_method: 'card_test',
        shipping_address: {
          line1: '123 Test Street',
          city: 'London',
          postcode: 'EC1A 1BB',
        },
      }),
      { headers: getHeaders(token) },
    );

    const checkoutOk = check(res, {
      'checkout status 201':    (r) => r.status === 201,
      'order ID returned':      (r) => {
        try {
          return !!JSON.parse(r.body).order_id;
        } catch {
          return false;
        }
      },
      'checkout within 2s':     (r) => r.timings.duration < 2000,
    });

    checkoutDuration.add(Date.now() - startTime);

    if (!checkoutOk) {
      checkoutErrors.add(1);
      console.error(`Checkout failed: HTTP ${res.status} — ${res.body}`);
    }

    sleep(2);
  });
}
