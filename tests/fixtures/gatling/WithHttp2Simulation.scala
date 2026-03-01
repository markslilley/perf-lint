import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class WithHttp2Simulation extends Simulation {

  val httpProtocol = http
    .baseUrl("https://staging.example.com")
    .enableHttp2

  val scn = scenario("With HTTP2")
    .exec(http("Home Page").get("/"))
    .pause(1)

  setUp(
    scn.inject(rampUsers(50).during(60))
  ).protocols(httpProtocol)
    .assertions(
      global.responseTime.percentile(95).lt(500)
    )
}
