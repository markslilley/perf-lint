import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class WithCheckSimulation extends Simulation {

  val httpProtocol = http
    .baseUrl("https://staging.example.com")

  val scn = scenario("With Checks")
    .exec(http("Home Page")
      .get("/")
      .check(status.is(200))
    )
    .pause(1)
    .exec(http("Search")
      .get("/search")
      .check(status.is(200))
    )
    .pause(1)

  setUp(
    scn.inject(rampUsers(50).during(60))
  ).protocols(httpProtocol)
    .assertions(
      global.responseTime.percentile(95).lt(500)
    )
}
