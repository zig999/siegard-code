import sys, os, tempfile
sys.path.insert(0, "/home/siegfriedneto/projects/siegard-code/dist/.claude/lib")
d = tempfile.mkdtemp(); os.environ["ORCH_PROJECT_DIR"]=d; os.environ["ORCH_SNAPSHOT"]="0"
import orch_core as oc
oc.install_transition_preconditions()
PH=[{"name":"sdd","order":1,"required":True},{"name":"dev","order":2,"required":True},
    {"name":"review","order":3,"required":True},{"name":"test","order":4,"required":True}]
A=lambda t,dd: oc.append_event(agent="audit",event_type=t,data=dd)
A("phase_declared",{"workflow_id":"wf1","phases":PH})
A("phase_entered",{"phase":"sdd","order":1,"workflow_id":"wf1"})
A("phase_exit_approved",{"phase":"sdd","criteria_met":["x"],"next_phase":"dev","workflow_id":"wf1"})
A("phase_transitioned",{"from_phase":"sdd","to_phase":"dev","evidence_seq":2,"workflow_id":"wf1"})
A("phase_entered",{"phase":"dev","order":2,"workflow_id":"wf1"})
A("phase_exit_approved",{"phase":"dev","criteria_met":["x"],"next_phase":"review","workflow_id":"wf1"})
A("phase_transitioned",{"from_phase":"dev","to_phase":"review","evidence_seq":5,"workflow_id":"wf1"})
A("phase_entered",{"phase":"review","order":3,"workflow_id":"wf1"})
A("phase_transitioned",{"from_phase":"review","to_phase":"dev","evidence_seq":8,"workflow_id":"wf1"})  # return
A("phase_entered",{"phase":"dev","order":2,"workflow_id":"wf1"})
# 2nd forward dev->review WITHOUT a fresh phase_exit_approved for the rework pass:
try:
    A("phase_transitioned",{"from_phase":"dev","to_phase":"review","evidence_seq":10,"workflow_id":"wf1"})
    print("STALE-APPROVAL: dev->review transition ACCEPTED with only the FIRST-pass approval (no fresh phase_exit_approved after re-entry)")
except oc.PreconditionViolation as e:
    print("stale approval rejected:", e)
# Now cross-check the review->test human gate satisfied by an approve from a DIFFERENT workflow:
d2 = tempfile.mkdtemp(); os.environ["ORCH_PROJECT_DIR"]=d2
import importlib; importlib.reload(oc); oc.install_transition_preconditions()
A=lambda t,dd: oc.append_event(agent="audit",event_type=t,data=dd)
A("phase_declared",{"workflow_id":"other","phases":PH})
A("human_response",{"escalation_seq":1,"action":"approve","operator":"op"})  # approval belonging to workflow 'other'
A("phase_declared",{"workflow_id":"wf2","phases":PH})
A("phase_entered",{"phase":"sdd","order":1,"workflow_id":"wf2"})
A("phase_exit_approved",{"phase":"sdd","criteria_met":["x"],"next_phase":"dev","workflow_id":"wf2"})
A("phase_transitioned",{"from_phase":"sdd","to_phase":"dev","evidence_seq":4,"workflow_id":"wf2"})
A("phase_entered",{"phase":"dev","order":2,"workflow_id":"wf2"})
A("phase_exit_approved",{"phase":"dev","criteria_met":["x"],"next_phase":"review","workflow_id":"wf2"})
A("phase_transitioned",{"from_phase":"dev","to_phase":"review","evidence_seq":7,"workflow_id":"wf2"})
A("phase_entered",{"phase":"review","order":3,"workflow_id":"wf2"})
A("phase_exit_approved",{"phase":"review","criteria_met":["x"],"next_phase":"test","workflow_id":"wf2"})
try:
    A("phase_transitioned",{"from_phase":"review","to_phase":"test","evidence_seq":10,"workflow_id":"wf2"})
    print("CROSS-WF GATE LEAK: review->test in wf2 ACCEPTED using workflow 'other''s human approve")
except oc.PreconditionViolation as e:
    print("cross-workflow approve rejected:", e)
