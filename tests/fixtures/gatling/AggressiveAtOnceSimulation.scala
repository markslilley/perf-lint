import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class AggressiveAtOnceSimulation extends Simulation {

  val httpProtocol = http
    .baseUrl("https://staging.example.com")

  val scn = scenario("Aggressive At Once")
    .exec(http("Home Page").get("/"))
    .pause(1)

  setUp(
    scn.inject(atOnceUsers(50))
  ).protocols(httpProtocol)
    .assertions(
      global.responseTime.percentile(95).lt(500)
    )
}
