from schnippo import jobs as J


def test_interrupted_job_is_listed_with_its_last_stage(tmp_path):
    js = J.Jobs(tmp_path)
    job = js.start("build", {"name": "X"}, "X (polish)", "/m")
    js.stage(job, "timeline", {"tmp": "X_V4_Polish_unvollstaendig", "final": "X_V4_Polish"})
    js.stage(job, "overlays")
    assert js.open_jobs() == []  # still running in this process
    J._ACTIVE.discard(job["id"])  # what a crash/kill looks like to the next server process
    (o,) = js.open_jobs()
    assert o["status"] == "unterbrochen" and o["stages"] == ["timeline", "overlays"]
    assert o["info"]["tmp"].endswith("_unvollstaendig")
    js.finish(o, "fortgesetzt")
    assert js.open_jobs() == []
    done = js.start("transcribe", {}, "t", None)
    js.finish(done, "fehlgeschlagen", "Clips ohne Ergebnis: c02")
    assert [j["id"] for j in js.open_jobs()] == [done["id"]]
