/** Scala 2.13+ zero-dependency incident-window classification. */
object IncidentWindow {
  final case class Summary(total: Int, breaches: Int, maximumMs: Double) {
    def breachRate: Double = if (total == 0) 0d else breaches.toDouble / total
  }

  def summarize(latencies: Seq[Double], thresholdMs: Double): Summary = {
    require(thresholdMs > 0 && !thresholdMs.isNaN && !thresholdMs.isInfinity,
      "threshold must be finite and positive")
    require(latencies.forall(x => x >= 0 && !x.isNaN && !x.isInfinity),
      "latencies must be finite and nonnegative")
    Summary(latencies.size, latencies.count(_ > thresholdMs),
      if (latencies.isEmpty) 0d else latencies.max)
  }

  def main(args: Array[String]): Unit = {
    assert(summarize(Seq(10, 120, 200), 100) == Summary(3, 2, 200))
    assert(summarize(Seq.empty, 100).breachRate == 0d)
    try {
      summarize(Seq(-1), 100)
      sys.error("negative latency was accepted")
    } catch {
      case _: IllegalArgumentException => ()
    }
    println("Scala incident checks passed")
  }
}
