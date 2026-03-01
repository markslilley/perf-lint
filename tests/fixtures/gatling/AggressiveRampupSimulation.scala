import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class AggressiveRampupSimulation extends Simulation {

  val httpProtocol = http
    .baseUrl("https://staging.example.com")

  val scn = scenario("Aggressive Rampup")
    .exec(http("Home Page").get("/"))
    .pause(1)

  setUp(
    scn.inject(rampUsers(1000).during(5))  // 200 users/second — very aggressive!
  ).protocols(httpProtocol)
    .assertions(
      global.responseTime.percentile(95).lt(500)
    )
}
