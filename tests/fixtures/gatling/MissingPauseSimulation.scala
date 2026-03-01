import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class MissingPauseSimulation extends Simulation {

  val httpProtocol = http
    .baseUrl("https://staging.example.com")
    .acceptHeader("application/json")

  val scn = scenario("No Pauses")
    .exec(http("Home Page").get("/"))
    .exec(http("User Profile").get("/api/users/1"))
    .exec(http("Dashboard").get("/dashboard"))
    // No pause() calls!

  setUp(
    scn.inject(rampUsers(50).during(60))
  ).protocols(httpProtocol)
    .assertions(
      global.responseTime.percentile(95).lt(500)
    )
}
