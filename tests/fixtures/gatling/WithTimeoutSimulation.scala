import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class WithTimeoutSimulation extends Simulation {

  val httpProtocol = http
    .baseUrl("https://staging.example.com")
    .connectionTimeout(5.seconds)
    .readTimeout(30.seconds)

  val scn = scenario("With Timeout")
    .exec(http("Home Page").get("/"))
    .pause(1)

  setUp(
    scn.inject(rampUsers(50).during(60))
  ).protocols(httpProtocol)
    .assertions(
      global.responseTime.percentile(95).lt(500)
    )
}
