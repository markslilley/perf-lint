import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class EmptySimulation extends Simulation {

  val httpProtocol = http
    .baseUrl("https://staging.example.com")

  // No exec, no scenario — skeleton file
  setUp(
    scenario("Empty").inject(atOnceUsers(1))
  ).protocols(httpProtocol)
}
