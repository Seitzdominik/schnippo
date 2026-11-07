from schnippo.snap import describe, edge_gaps, snap_span

FPS = 30
CUTS = [0, 90, 150, 300, 420]  # timeline cuts in frames


def snap(a, b, **kw):
    args = dict(thr=18, sliver=15, margin=4, dmin=45, dmax=90, total=420)
    args.update(kw)
    return snap_span(a, b, CUTS, **args)


def test_edges_snap_onto_nearby_cuts():
    s = snap(95, 290)  # 5 F after a cut, 10 F before a cut; 195 F long → too long for dmax 90
    s = snap(95, 145)  # start 5 F after cut 90, end 5 F before cut 150
    assert (s.start, s.end) == (90, 150) and s.on_cut == (True, True) and s.moved == (-5, 5) and not s.warnings


def test_no_sliver_and_cover_margin():
    s = snap(100, 160)  # end 10 F after cut 150 → still visible cut right before the end → snap back
    assert s.end == 150 or s.end in CUTS
    assert snap(160, 230).start == 150  # start 10 F after a cut → face flashes 10 F → onto the cut


def test_far_edges_stay_and_duration_limits():
    s = snap(200, 260)  # both ≥ 40 F away from cuts → unchanged
    assert (s.start, s.end) == (200, 260) and s.moved == (0, 0)
    s = snap(92, 100, dmin=45)  # too short after snapping start → end extended to the next cut
    assert s.start == 90 and s.end == 150


def test_gaps_report():
    g = edge_gaps(90, 140, CUTS)
    assert g == {"start_after_cut": 0, "start_before_cut": 0, "end_after_cut": 50, "end_before_cut": 10}
    assert "eingerastet" in describe(snap(95, 145), FPS) and "0 (auf dem Schnitt)" in describe(snap(95, 145), FPS)
