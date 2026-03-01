import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class MultiRequestNoSaveAsSimulation extends Simulation {

  val httpProtocol = http
    .baseUrl("https://staging.example.com")

  val scn = scenario("Multi Request No SaveAs")
    .exec(http("Login").post("/login"))
    .pause(1)
    .exec(http("Dashboard").get("/dashboard"))
    .pause(1)

  setUp(
    scn.inject(rampUsers(50).during(60))
  ).protocols(httpProtocol)
    .assertions(
      global.responseTime.percentile(95).lt(500)
    )
}
