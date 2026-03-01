import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class HardcodedIPSimulation extends Simulation {

  val httpProtocol = http
    .baseUrl("http://192.168.1.100")  // Hardcoded IP!
    .acceptHeader("application/json")

  val scn = scenario("Hardcoded IP")
    .exec(http("Home Page").get("/"))
    .pause(1)
    .exec(http("API").get("/api/data"))
    .pause(1)

  setUp(
    scn.inject(rampUsers(20).during(60))
  ).protocols(httpProtocol)
    .assertions(
      global.responseTime.percentile(95).lt(500)
    )
}
