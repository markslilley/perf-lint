import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class GoodSimulation extends Simulation {

  val baseUrl = System.getProperty("baseUrl", "https://staging.example.com")

  val httpProtocol = http
    .baseUrl(baseUrl)
    .acceptHeader("application/json")
    .connectionTimeout(5.seconds)
    .readTimeout(30.seconds)
    .enableHttp2

  val feeder = csv("test-data.csv").random

  val scn = scenario("User Journey")
    .feed(feeder)
    .exec(
      http("Login")
        .post("/api/login")
        .check(status.is(200))
        .check(jsonPath("$.token").saveAs("authToken"))
    )
    .pause(1, 3)
    .exec(
      http("User Profile")
        .get("/api/users/${userId}")
        .header("Authorization", "Bearer #{authToken}")
        .check(status.is(200))
    )
    .pause(1, 2)
    .exec(
      http("Dashboard")
        .get("/dashboard")
        .header("Authorization", "Bearer #{authToken}")
        .check(status.is(200))
    )
    .pause(1, 3)

  setUp(
    scn.inject(rampUsers(100).during(60))
  ).protocols(httpProtocol)
    .maxDuration(10.minutes)
    .assertions(
      global.responseTime.percentile(95).lt(500),
      global.failedRequests.percent.lt(1)
    )
}
