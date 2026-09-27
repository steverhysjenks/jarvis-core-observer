import hashlib, json, sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
LOCAL_TIMEZONE=ZoneInfo("Europe/London"); DATABASE_PATH=Path("/var/lib/jarvis-core/jarvis.db")

def candidate_key(candidate: dict) -> str:
    identity={"type":candidate.get("type")}; candidate_type=candidate.get("type")
    if candidate_type=="possible_bins_not_put_out": identity.update({"collection_date":candidate.get("collection_date"),"collection_types":candidate.get("collection_types")})
    elif candidate_type=="routine_departure_deviation":
        routine=candidate.get("routine",{}); identity.update({"weekday":routine.get("weekday"),"typical_time":routine.get("typical_time")})
    else: identity["reason"]=candidate.get("reason")
    canonical=json.dumps(identity,sort_keys=True,separators=(",",":")); digest=hashlib.sha256(canonical.encode()).hexdigest()[:20]
    return f"{candidate_type or 'unknown'}:{digest}"

def _connect():
    c=sqlite3.connect(DATABASE_PATH); c.row_factory=sqlite3.Row; return c

def initialise_ledger():
    DATABASE_PATH.parent.mkdir(parents=True,exist_ok=True)
    with _connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS attention_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT,candidate_key TEXT NOT NULL,candidate_type TEXT NOT NULL,first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,seen_count INTEGER NOT NULL DEFAULT 1,mode TEXT NOT NULL,status TEXT NOT NULL,candidate_json TEXT NOT NULL,judgement TEXT,confidence REAL,reason TEXT,message TEXT,model TEXT)""")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_attention_ledger_candidate_key ON attention_ledger(candidate_key)")
        c.execute("""CREATE TABLE IF NOT EXISTS attention_observations (id INTEGER PRIMARY KEY AUTOINCREMENT,candidate_key TEXT NOT NULL,candidate_type TEXT NOT NULL,observed_at TEXT NOT NULL,mode TEXT NOT NULL,candidate_json TEXT NOT NULL,judgement TEXT,confidence REAL,reason TEXT,message TEXT,model TEXT)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_attention_observations_candidate_key ON attention_observations(candidate_key)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_attention_observations_observed_at ON attention_observations(observed_at)")
        c.commit()

def record_candidate(candidate: dict, mode="shadow", judgement=None, model=None):
    initialise_ledger(); key=candidate_key(candidate); now=datetime.now(LOCAL_TIMEZONE).isoformat(); payload=json.dumps(candidate,sort_keys=True)
    decision=confidence=reason=message=None
    if judgement: decision=judgement.get("decision"); confidence=judgement.get("confidence"); reason=judgement.get("reason"); message=judgement.get("message")
    with _connect() as c:
        existing=c.execute("SELECT * FROM attention_ledger WHERE candidate_key=?",(key,)).fetchone()
        if existing:
            c.execute("UPDATE attention_ledger SET last_seen=?,seen_count=seen_count+1,mode=?,candidate_json=?,judgement=?,confidence=?,reason=?,message=?,model=? WHERE candidate_key=?",(now,mode,payload,decision,confidence,reason,message,model,key)); status="existing"
        else:
            c.execute("INSERT INTO attention_ledger (candidate_key,candidate_type,first_seen,last_seen,seen_count,mode,status,candidate_json,judgement,confidence,reason,message,model) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(key,candidate.get("type","unknown"),now,now,1,mode,"observed",payload,decision,confidence,reason,message,model)); status="new"
        c.execute("INSERT INTO attention_observations (candidate_key,candidate_type,observed_at,mode,candidate_json,judgement,confidence,reason,message,model) VALUES (?,?,?,?,?,?,?,?,?,?)",(key,candidate.get("type","unknown"),now,mode,payload,decision,confidence,reason,message,model)); c.commit()
    return {"candidate_key":key,"ledger_status":status,"mode":mode}

def recent_entries(limit=50):
    initialise_ledger()
    with _connect() as c: rows=c.execute("SELECT candidate_key,candidate_type,first_seen,last_seen,seen_count,mode,status,judgement,confidence,reason,message,model FROM attention_ledger ORDER BY last_seen DESC LIMIT ?",(limit,)).fetchall()
    return [dict(r) for r in rows]

def recent_observations(limit=100):
    initialise_ledger()
    with _connect() as c: rows=c.execute("SELECT id,candidate_key,candidate_type,observed_at,mode,judgement,confidence,reason,message,model FROM attention_observations ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
    return [dict(r) for r in rows]
