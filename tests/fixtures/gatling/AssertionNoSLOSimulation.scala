import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class AssertionNoSLOSimulation extends Simulation {

  val httpProtocol = http
    .baseUrl("https://staging.example.com")

  val scn = scenario("Assertion No SLO")
    .exec(http("Home Page").get("/"))
    .pause(1)

  setUp(
    scn.inject(rampUsers(50).during(60))
  ).protocols(httpProtocol)
    .assertions(
      global.successfulRequests.count.gt(0)
    )
}
