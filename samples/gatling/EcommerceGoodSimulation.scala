import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

/**
 * Gatling Simulation — E-commerce checkout flow (GOOD example)
 *
 * Demonstrates best practices:
 *   - Base URL from system property (not hardcoded)
 *   - CSV feeder for varied test data
 *   - pause() between requests (realistic think time)
 *   - Assertions to enforce SLOs
 *   - Gradual ramp-up (not a spike)
 *   - Named requests for clear reporting
 *
 * Run:
 *   mvn gatling:test \
 *     -DbaseUrl=https://staging.example.com \
 *     -DusersFile=users.csv \
 *     -DproductsFile=products.csv
 */
class EcommerceGoodSimulation extends Simulation {

  // ── Configuration ───────────────────────────────────────────────────────────
  val baseUrl    = System.getProperty("baseUrl",    "https://staging.example.com")
  val numUsers   = System.getProperty("users",      "50").toInt
  val rampSecs   = System.getProperty("rampSecs",   "120").toInt
  val holdSecs   = System.getProperty("holdSecs",   "600").toInt

  // ── Protocol ────────────────────────────────────────────────────────────────
  val httpProtocol = http
    .baseUrl(baseUrl)
    .acceptHeader("application/json")
    .contentTypeHeader("application/json")
    .acceptLanguageHeader("en-GB,en;q=0.9")
    .userAgentHeader("Mozilla/5.0 (Gatling load test)")

  // ── Feeders ─────────────────────────────────────────────────────────────────
  val userFeeder    = csv("users.csv").random
  val productFeeder = csv("products.csv").random

  // ── Scenario ─────────────────────────────────────────────────────────────────
  val checkoutScenario = scenario("E-commerce Checkout")

    // Pick a user and product from the feeders
    .feed(userFeeder)
    .feed(productFeeder)

    // 1. Homepage
    .exec(
      http("01 GET Homepage")
        .get("/")
        .check(status.is(200))
        .check(responseTimeInMillis.lt(1000))
    )
    .pause(2, 5)  // User spends 2–5 seconds on the homepage

    // 2. Browse products
    .exec(
      http("02 GET Products")
        .get("/api/products?limit=20")
        .check(status.is(200))
        .check(jsonPath("$.items").exists)
        .check(jsonPath("$.items[0].id").saveAs("productId"))
    )
    .pause(3, 8)  // User browses for 3–8 seconds

    // 3. View product detail
    .exec(
      http("03 GET Product Detail")
        .get("/api/products/#{productId}")
        .check(status.is(200))
        .check(jsonPath("$.price").exists)
    )
    .pause(5, 15)  // User reads the product page for 5–15 seconds

    // 4. Log in
    .exec(
      http("04 POST Login")
        .post("/api/auth/login")
        .body(StringBody("""{"email":"#{userEmail}","password":"#{userPassword}"}"""))
        .check(status.is(200))
        .check(jsonPath("$.token").saveAs("authToken"))
    )
    .pause(1, 2)

    // 5. Add to cart
    .exec(
      http("05 POST Add to Cart")
        .post("/api/cart/items")
        .header("Authorization", "Bearer #{authToken}")
        .body(StringBody("""{"product_id":"#{productId}","quantity":1}"""))
        .check(status.is(201))
    )
    .pause(2, 4)

    // 6. Checkout
    .exec(
      http("06 POST Checkout")
        .post("/api/orders")
        .header("Authorization", "Bearer #{authToken}")
        .body(StringBody(
          """{
            |  "payment_method": "card_test",
            |  "shipping_address": {
            |    "line1": "123 Test Street",
            |    "city": "London",
            |    "postcode": "EC1A 1BB"
            |  }
            |}""".stripMargin
        ))
        .check(status.is(201))
        .check(jsonPath("$.order_id").exists)
        .check(responseTimeInMillis.lt(3000))
    )
    .pause(2, 3)

  // ── Load injection ───────────────────────────────────────────────────────────
  setUp(
    checkoutScenario.inject(
      nothingFor(5.seconds),                         // Brief warm-up pause
      rampUsers(numUsers).during(rampSecs.seconds),  // Gradual ramp-up
      constantUsersPerSec(numUsers / 10.0)           // Sustain at target rate
        .during(holdSecs.seconds)
    )
  )
  .protocols(httpProtocol)
  .assertions(
    // Global assertions — these cause the simulation to FAIL if breached
    global.responseTime.percentile(95).lt(500),    // p95 < 500ms
    global.responseTime.percentile(99).lt(1500),   // p99 < 1.5s
    global.failedRequests.percent.lt(1),           // Error rate < 1%
    // Per-request assertions for critical paths
    details("06 POST Checkout").responseTime.percentile(95).lt(2000)
  )
}
