"""本机编译两个内置 AI，以真实 JSON 协议和后端引擎交叉验证。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app import engine as E


@pytest.fixture(scope="module")
def binaries(tmp_path_factory):
    compiler = shutil.which("g++")
    if compiler is None:
        pytest.skip("需要本机 g++")
    source = Path(__file__).resolve().parents[1]/"app"/"ai_cpp_example"
    folder = tmp_path_factory.mktemp("event_ai")
    result = {}
    for name in ("ai_example", "ai_random"):
        exe = folder/(name+".exe")
        subprocess.run([compiler,"-std=c++17","-O2","-finput-charset=UTF-8",str(source/(name+".cpp")),"-o",str(exe)],check=True)
        result[name] = exe
    return result


def ask(exe, payload):
    r = subprocess.run([str(exe)],input=json.dumps(payload),text=True,capture_output=True,check=True,timeout=10)
    return json.loads(r.stdout)


@pytest.mark.parametrize("name", ["ai_example", "ai_random"])
@pytest.mark.parametrize("size", [9, 15])
def test_cpp_decisions_execute(binaries,name,size):
    st = E.new_game(n=size,m=size,seed=53,event_limit=48)
    for player in (0,1):
        E.select_skills(st,player,["double_move"]*st.skill_k)
        st.hands[player] = {s:2 for s in E.SKILLS}
    while st.winner is None:
        before = st.events
        d = ask(binaries[name],st.to_ai_dict())
        assert "actions" not in d
        E.apply_event(st,d)
        assert st.events == before+1
    assert st.events <= 48


@pytest.mark.parametrize("name", ["ai_example", "ai_random"])
def test_cpp_forced_move_and_preparation_phases(binaries,name):
    st = E.new_game(n=9,m=9,seed=71)
    payload = dict(n=9,m=9,deads=sorted(st.deads),sands=sorted(st.sands))
    goals = ask(binaries[name],dict(payload,phase="goals"))
    E.validate_goal_sets(9,goals["goal_A"],goals["goal_B"])
    assert ask(binaries[name],dict(payload,**goals,phase="side"))["side"] in ("first","second")
    picks = ask(binaries[name],dict(payload,**goals,phase="select",skill_k=2))["skills"]
    assert len(picks)==2 and all(s in E.SKILLS for s in picks)
    for player in (0,1):E.select_skills(st,player,["double_move"]*st.skill_k)
    E.play_skill(st,"double_move")
    for _ in range(2):
        d=ask(binaries[name],st.to_ai_dict())
        assert "skill" not in d and d["action"]["type"]=="move"
        E.apply_event(st,d)
        if st.turn!=0:break
    assert st.events in (1,2)
