"""单事件协议、事件预算、回放与容器启动参数回归。"""
import json
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import ai_runner as runner, engine as E
from app.main import app, GAMES


def board(limit=800):
    return E.GameState(n=9, m=9, walls_total=10, pawns=[[0, 4], [8, 4]],
                       walls_left=[10, 10], goal_A=[0, 1, 2, 3], goal_B=[5, 6, 7, 8],
                       hands=[{s: 2 for s in E.SKILLS}, {s: 2 for s in E.SKILLS}], event_limit=limit)


def move(r, c, skill=None):
    d = {"action": {"type": "move", "to": [r, c]}}
    if skill:
        d["skill"] = skill
    return d


def test_double_requests_new_state(monkeypatch):
    st = board()
    snapshots = []
    answers = iter([move(1, 4, "double_move"), move(2, 4)])
    def run(*args):
        snapshots.append(args[1])
        return next(answers)
    monkeypatch.setattr(runner, "run_ai", run)
    runner._step_side("ai", st, 5)
    assert st.events == 1 and st.turn == 0 and st.must_move
    runner._step_side("ai", st, 5)
    assert st.events == 2 and st.turn == 1 and not st.must_move
    assert snapshots[1]["pawns"][0] == [1, 4]
    assert snapshots[1]["remaining_moves"] == 1
    assert snapshots[1]["skill_used"] and snapshots[1]["must_move"]
    assert snapshots[1]["remaining_events"] == 799


def test_sand_is_separate_event_and_locks_skill():
    st = board()
    E.apply_event(st, {"skill": "make_sand", "to": [4, 4]})
    assert st.events == 1 and st.turn == 0 and st.seq_skill_used
    assert (4, 4) in st.to_ai_dict()["sands"]
    before = st.to_dict()
    with pytest.raises(ValueError):
        E.apply_event(st, move(1, 4, "phase_walk"))
    assert st.to_dict() == before
    E.apply_event(st, move(1, 4))
    assert st.events == 2 and st.turn == 1


@pytest.mark.parametrize("decision", [
    {"skill": "free_wall"},
    {"skill": "make_sand", "to": [4, 4], "action": {"type": "move", "to": [1, 4]}},
    {"actions": [{"type": "move", "to": [1, 4]}]},
    move(5, 5, "double_move"),
])
def test_invalid_event_is_atomic(decision):
    st = board(); before = st.to_dict()
    with pytest.raises(ValueError):
        E.apply_event(st, decision)
    assert st.to_dict() == before


def test_must_move_and_skill_lock():
    st = board(); E.apply_event(st, move(1, 4, "double_move")); before = st.to_dict()
    for d in ({"action": {"type": "wall", "wall": {"wr": 3, "wc": 3, "orientation": "H"}}},
              move(2, 4, "phase_walk")):
        with pytest.raises(ValueError): E.apply_event(st, d)
        assert st.to_dict() == before


def test_sand_overrides_double_and_new_snapshot():
    st = board(); st.sands.add((1, 4))
    E.apply_event(st, move(1, 4, "double_move"))
    x = st.to_ai_dict()
    assert st.events == 1 and x["turn"] == 1 and x["remaining_moves"] == 2
    assert not x["must_move"] and not x["skill_used"] and x["sand_bonus"]


@pytest.mark.parametrize("skill,action,key", [
    ("phase_walk", {"type": "wall", "wall": {"wr": 3, "wc": 3, "orientation": "H"}}, "phase_buff"),
    ("free_wall", {"type": "move", "to": [1, 4]}, "free_buff"),
])
def test_persistent_effects_exported(skill, action, key):
    st = board(); E.apply_event(st, {"skill": skill, "action": action})
    assert st.events == 1 and st.to_ai_dict()[key][0]
    E.apply_event(st, move(7, 4))
    assert st.to_ai_dict()[key][0] and st.turn == 0
    assert E.GameState.from_dict(st.to_dict()).to_ai_dict() == st.to_ai_dict()


def test_public_snapshot_and_pending_l():
    st = board(); E.play_skill(st, "l_remodel")
    x = st.to_ai_dict()
    assert x["l_pending"] == [True, False] and x["l_bonus"] == [1, 0]
    assert x["skill_used"] and x["events"] == 0 and x["protocol_version"] == 2
    assert x["hand"]["l_remodel"] == 1 and x["opp_hand_count"] == 10
    assert "hands" not in x and "history" not in x


@pytest.mark.parametrize("decision", [move(1, 4), move(1, 4, "double_move"),
    {"skill": "make_sand", "to": [4, 4]},
    {"skill": "free_wall", "action": {"type": "wall", "wall": {"wr": 3, "wc": 3, "orientation": "H"}}}])
def test_cap_after_exactly_one_event(decision):
    st = board(1); E.apply_event(st, decision)
    assert st.events == 1 and st.winner == -1 and st.to_ai_dict()["remaining_events"] == 0
    with pytest.raises(ValueError): E.apply_event(st, move(2, 4))
    assert st.events == 1


def test_goal_on_last_event_wins():
    st = board(1); st.pawns[0] = [7, 2]
    E.apply_event(st, move(8, 2))
    assert st.events == 1 and st.winner == 0


def test_match_count_and_replay(monkeypatch):
    monkeypatch.setattr(runner, "ensure_image", lambda *a: None)
    monkeypatch.setattr(runner, "select_for", lambda *a: ["make_sand", "double_move"])
    monkeypatch.setattr(runner, "ai_side", lambda *a: "first")
    def run(aid, x, *args):
        if x["events"] == 0: return {"skill": "make_sand", "to": [4, 4]}
        st = E.GameState(n=x["n"], m=x["m"], walls_total=10, pawns=x["pawns"], walls_left=x["walls_left"],
                         deads=set(map(tuple, x["deads"])), sands=set(map(tuple, x["sands"])),
                         goal_A=x["goal_A"], goal_B=x["goal_B"])
        r, c = E.legal_pawn_moves(st, x["turn"])[0]
        return move(r, c)
    monkeypatch.setattr(runner, "run_ai", run)
    progress = []
    r = runner.play_match("random", "random", 9, 9, 11, 4, on_ply=progress.append)
    assert progress == [1, 2, 3, 4] and r["plies"] == 4 and r["winner"] == -1
    assert len(r["log"]) == 4 and r["state"]["events"] == 4
    job = dict(games=1, white="random", black="random", results=[dict(index=0,winner_seat=-1,win_reason=r["win_reason"],plies=4)], tables=[r])
    monkeypatch.setitem(runner.JOBS, "event-replay", job)
    replay = runner.rebuild_batch_game("event-replay", 0)
    assert [s["events"] for s in replay["states"]] == [0, 1, 2, 3, 4]
    assert replay["states"][-1] == r["state"]


def test_docker_no_cpu_quota(monkeypatch):
    monkeypatch.setattr(runner, "ensure_image", lambda *a: None)
    calls = []
    def run(args, **kwargs):
        calls.append(args); return SimpleNamespace(returncode=0, stdout=json.dumps(move(1, 4)), stderr="")
    monkeypatch.setattr(subprocess, "run", run)
    runner.run_ai("ai", board().to_ai_dict())
    assert not any(x.startswith("--cpu") for x in calls[0])
    assert "--network" in calls[0] and "--memory=256m" in calls[0]


def test_http_event_limit_and_second_move(monkeypatch):
    c = TestClient(app)
    g = c.post("/api/games/new", json={"n": 9, "m": 9, "seed": 3, "event_limit": 2}).json()
    gid = g["id"]; st = GAMES[gid]; st.deads.clear(); st.sands.clear()
    for player in (0, 1): E.select_skills(st, player, ["double_move"]*st.skill_k)
    answers = iter([move(1, 4, "double_move"), move(2, 4)])
    monkeypatch.setattr(runner, "run_ai", lambda *a: next(answers))
    a = c.post(f"/api/games/{gid}/ai-external-move", json={"aid": "test"}).json()["state"]
    assert a["turn"] == 0 and a["events"] == 1 and a["winner"] is None
    b = c.post(f"/api/games/{gid}/ai-external-move", json={"aid": "test"}).json()["state"]
    assert b["events"] == 2 and b["winner"] == -1
