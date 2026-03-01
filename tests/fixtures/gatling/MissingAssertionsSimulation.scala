import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class MissingAssertionsSimulation extends Simulation {

  val httpProtocol = http
    .baseUrl("https://staging.example.com")
    .acceptHeader("application/json")

  val scn = scenario("No Assertions")
    .exec(http("Home Page").get("/"))
    .pause(1)
    .exec(http("Dashboard").get("/dashboard"))
    .pause(1)

  setUp(
    scn.inject(rampUsers(50).during(60))
  ).protocols(httpProtocol)
  // No assertions!
}
