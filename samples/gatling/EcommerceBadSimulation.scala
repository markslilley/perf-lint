import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

/**
 * Gatling Simulation — E-commerce checkout flow (BAD example)
 *
 * This simulation has several common quality problems that perf-lint will catch:
 *
 *   GAT001 — No pause() calls (VUs hammer the server without any think time)
 *   GAT002 — Hardcoded IP address in baseUrl
 *   GAT003 — No assertions (SLOs can't be enforced, failures go undetected)
 *   GAT004 — Aggressive ramp-up (1000 users in 5 seconds = 200 users/second!)
 *   GAT005 — No feeder (all virtual users send identical requests)
 *
 * Run:
 *   mvn gatling:test -Dsimulation=EcommerceBadSimulation
 *
 * Then compare with EcommerceGoodSimulation.scala to see how to fix each issue.
 */
class EcommerceBadSimulation extends Simulation {

  // GAT002: Hardcoded IP — this simulation only works against one specific server
  // and can't be promoted through environments (dev → staging → prod)
  val httpProtocol = http
    .baseUrl("http://10.0.1.42:8080")
    .acceptHeader("application/json")

  // GAT005: No feeder — all 1000 virtual users will log in as the same user
  // and add the same product to their cart. This creates artificial hotspots
  // and doesn't reflect real traffic patterns.

  val checkoutScenario = scenario("E-commerce Checkout")

    // GAT001: No pause() between requests — VUs execute requests as fast as
    // possible, which is physically impossible for a real human.
    // This creates unrealistic load patterns and will produce misleading results.

    .exec(
      http("Homepage")
        .get("/")
        // GAT003: No check() — if this returns a 500, the scenario continues
    )

    .exec(
      http("Login")
        .post("/api/auth/login")
        // GAT005: Same hardcoded credentials for all 1000 virtual users
        .body(StringBody("""{"email":"testuser@example.com","password":"password123"}"""))
        // GAT003: No status check — failed logins are silently ignored
    )

    .exec(
      http("Add to Cart")
        .post("/api/cart/items")
        // GAT005: All users add the exact same product
        .body(StringBody("""{"product_id":"PRD-001","quantity":1}"""))
        // GAT003: No assertion on the cart response
    )

    .exec(
      http("Checkout")
        .post("/api/orders")
        .body(StringBody("""{"payment_method":"card_test"}"""))
        // GAT003: No assertion on the most critical step — we'll never know if
        // checkout broke under load
    )

  setUp(
    // GAT004: 1000 users ramping in just 5 seconds = 200 users/second.
    // This is an unrealistic spike that will overwhelm most systems.
    // A realistic ramp would take at least 100 seconds for 1000 users.
    checkoutScenario.inject(
      rampUsers(1000).during(5)
    )
  ).protocols(httpProtocol)
  // GAT003: No assertions — this simulation will always "pass" regardless of
  // response times or error rates. It's useless as a quality gate.
}
