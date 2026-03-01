import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class NoMaxDurationSimulation extends Simulation {

  val httpProtocol = http
    .baseUrl("https://staging.example.com")

  val scn = scenario("No Max Duration")
    .exec(http("Home Page").get("/"))
    .pause(1)

  setUp(
    scn.inject(rampUsers(100).during(60))
  ).protocols(httpProtocol)
    .assertions(
      global.responseTime.percentile(95).lt(500)
    )
}
