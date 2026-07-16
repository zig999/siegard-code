import sys, os, json, tempfile
sys.path.insert(0, "/home/siegfriedneto/projects/siegard-code/dist/.claude/lib")

def run_scenario(events, label):
    d = tempfile.mkdtemp()
    os.environ["ORCH_PROJECT_DIR"] = d
    os.environ["ORCH_SNAPSHOT"] = "0"
    # re-import fresh module paths
    for m in list(sys.modules):
        if m == "orch_core":
            del sys.modules[m]
    import orch_core as oc
    oc.install_transition_preconditions()
    for (etype, data) in events:
        oc.append_event(agent="audit", event_type=etype, data=data)
    state = oc.reduce_all()
    phases = [{"required": p.required, "status": p.status if isinstance(p.status,str) else p.status.value, "name": p.name, "order": p.order} for p in state.phases.values()]
    rs = oc._m3_derive_run_status({"raw_run_status": state.run_status, "phases": phases})
    pending = sorted([p for p in phases if p["status"]=="pending"], key=lambda p:p["order"])
    print(f"--- {label} ---")
    for p in sorted(phases, key=lambda x:x['order']):
        print(f"  {p['name']:8s} {p['status']}")
    print(f"  current_phase={state.current_phase}  M3 run_status={rs}  lowest_pending={pending[0]['name'] if pending else None}")

PH = [{"name":"sdd","order":1,"required":True},{"name":"dev","order":2,"required":True},
      {"name":"review","order":3,"required":True},{"name":"test","order":4,"required":True}]
W = "wf1"
def declared(): return ("phase_declared", {"workflow_id":W,"phases":PH})
def entered(p,o): return ("phase_entered", {"phase":p,"order":o,"workflow_id":W})
def approved(p,n): return ("phase_exit_approved", {"phase":p,"criteria_met":["x"],"next_phase":n,"workflow_id":W})
def trans(f,t,ev): return ("phase_transitioned", {"from_phase":f,"to_phase":t,"evidence_seq":ev,"workflow_id":W})
def human_approve(): return ("human_response", {"escalation_seq":1,"action":"approve","operator":"op"})

# Scenario A: test -> dev return, then dev re-completes
evA = [declared(), entered("sdd",1), approved("sdd","dev"), trans("sdd","dev",2),
       entered("dev",2), approved("dev","review"), trans("dev","review",5),
       entered("review",3), approved("review","test"), human_approve(), trans("review","test",9),
       entered("test",4),
       trans("test","dev",12),                       # RETURN (exempt from preconditions)
       entered("dev",2), approved("dev","review"), trans("dev","review",14)]  # dev re-completes
run_scenario(evA, "A: test->dev return, dev re-completes (no re-review, no re-test)")

# Scenario B: review -> dev return, then dev re-completes
evB = [declared(), entered("sdd",1), approved("sdd","dev"), trans("sdd","dev",2),
       entered("dev",2), approved("dev","review"), trans("dev","review",5),
       entered("review",3),
       trans("review","dev",8),                      # RETURN after human return_to_dev
       entered("dev",2), approved("dev","review"), trans("dev","review",10)]  # dev re-completes
run_scenario(evB, "B: review->dev return, dev re-completes (review never re-entered)")
