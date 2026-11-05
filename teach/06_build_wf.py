import json, uuid
_c=[0]
def nid():
    _c[0]+=1
    return str(uuid.uuid5(uuid.NAMESPACE_URL,'harborridge-n8n-%d'%_c[0]))  # deterministic: stable form/webhook URLs
def node(name,typ,ver,pos,params,**kw):
    d={"parameters":params,"id":nid(),"name":name,"type":typ,"typeVersion":ver,"position":pos}; d.update(kw); return d
def conn(*pairs):
    c={}
    for src,out,dst in pairs:
        c.setdefault(src,{"main":[]})
        m=c[src]["main"]
        while len(m)<=out: m.append([])
        m[out].append({"node":dst,"type":"main","index":0})
    return c
def wf(name,nodes,connections,settings=None):
    return {"name":name,"nodes":nodes,"connections":connections,"active":False,
            "settings":settings or {"executionOrder":"v1","timezone":"America/Chicago","saveManualExecutions":True},
            "pinData":{},"meta":{"templateCredsSetupCompleted":False},"tags":[]}

CONFIG_JS = r"""// ===== CONFIG: edit here only =====
const CONFIG = {
  provider: 'gemini',            // 'gemini' | 'ollama'  (switch to backup in one edit)
  aiEnabled: true,               // false = every item goes to the manual review queue
  geminiModel: 'gemini-3.1-flash-lite',
  ollamaModel: 'llama3.2',
  // Docker build: http://host.docker.internal:11434 ; npm/native install on the same host: http://127.0.0.1:11434 (not localhost, which can resolve to IPv6 ::1)
  ollamaUrl: 'http://host.docker.internal:11434',
  confidenceThreshold: 0.75,
  // Backup threshold is stricter: llama3.2 confidence is not calibrated (about 0.8 for almost everything).
  ollamaConfidenceThreshold: 0.85,
  // Routing teams, one line each. Descriptions are required for good routing with llama3.2.
  // To add a team (curveball: Catastrophe claim), copy one line and edit the name and description.
  teams: [
    { name: 'Claims', description: 'reporting a new loss or damage, or asking about an existing claim, adjuster or claim payment' },
    { name: 'Billing and Payments', description: 'premium payments, autopay, due dates, declined cards, refunds, late fees, payment plans, double charges' },
    { name: 'Policy Service', description: 'changes to an existing policy: add or remove a driver or vehicle, address change, deductible change, ID cards, paperless' },
    { name: 'New Business and Underwriting', description: 'quotes and applications for new policies or new customers' },
    { name: 'Agent Services', description: 'messages from insurance agencies or agents: portal access, commissions, binding authority' },
    { name: 'Complaints Unit', description: 'dissatisfaction, repeated unanswered requests, threats to cancel, mentions of a regulator, attorney or Department of Insurance' },
    { name: 'General Inquiries', description: 'too vague to tell what is needed, or general questions such as office hours' }
  ]
};
"""

NORMALIZE_JS = CONFIG_JS + r"""
const out = [];
for (const it of $input.all()) {
  const j = it.json;
  const id = j.item_id || j['Item ID'] || ('HR-' + $now.toFormat('yyyyMMdd-HHmmss') + '-' + Math.floor(Math.random()*1000).toString().padStart(3,'0'));
  const subject = (j.subject || j['Subject'] || '').toString().trim();
  const body = (j.body || j['Email body'] || '').toString().trim();
  const sender = (j.sender || j['Sender name'] || 'Unknown').toString().trim();
  const emailText = `From: ${sender}\nSubject: ${subject}\n\n${body}`.slice(0, 6000);
  const teamList = CONFIG.teams.map(t => '- ' + t.name + ': ' + t.description).join('\n');
  const systemPrompt =
`You are an internal email triage assistant for Harbor Ridge Mutual Insurance customer service.
You only PROPOSE a routing. A person reviews uncertain items. You never decide claims, coverage, payment or denial questions and never draft replies to customers.
Choose exactly one team from this list:
${teamList}
Rules:
1. complaint_flag = true if the message expresses dissatisfaction, repeats an unanswered request, threatens to cancel or complain, or mentions a regulator, the Department of Insurance, an attorney or the media. A complaint is routed to "Complaints Unit" even if it also asks about billing or claims; put the other topic in secondary_team.
2. urgency: "high" for complaints, regulator mentions, injury, active loss or cancellation threats; "medium" for time-bound requests; otherwise "low".
3. confidence is your probability (0 to 1) that the team is correct. Use below 0.6 when the message is ambiguous, mixes topics or is not in English.
4. reason: one sentence, no customer personal data.
5. language: ISO code of the email language.
Return JSON only.`;
  out.push({ json: {
    item_id: id, received_at: $now.toISO(), sender, subject, body,
    expected_team: j.expected_team || '', expected_complaint: j.expected_complaint || '',
    source: j.expected_team !== undefined ? 'batch_test' : 'form',
    provider: CONFIG.provider, ai_enabled: CONFIG.aiEnabled,
    model: CONFIG.provider === 'gemini' ? CONFIG.geminiModel : CONFIG.ollamaModel,
    gemini_model: CONFIG.geminiModel, ollama_model: CONFIG.ollamaModel, ollama_url: CONFIG.ollamaUrl,
    threshold: CONFIG.provider === 'gemini' ? CONFIG.confidenceThreshold : CONFIG.ollamaConfidenceThreshold,
    gemini_threshold: CONFIG.confidenceThreshold, ollama_threshold: CONFIG.ollamaConfidenceThreshold,
    teams: CONFIG.teams.map(t => t.name),
    system_prompt: systemPrompt, email_text: emailText
  }});
}
return out;
"""

GEMINI_BODY = r"""={{ JSON.stringify({
  systemInstruction: { parts: [{ text: $json.system_prompt }] },
  contents: [{ role: 'user', parts: [{ text: 'Triage this email:\n\n' + $json.email_text }] }],
  generationConfig: {
    temperature: 0,
    responseMimeType: 'application/json',
    responseSchema: {
      type: 'OBJECT',
      properties: {
        team: { type: 'STRING', enum: $json.teams },
        secondary_team: { type: 'STRING' },
        intent: { type: 'STRING' },
        urgency: { type: 'STRING', enum: ['low','medium','high'] },
        complaint_flag: { type: 'BOOLEAN' },
        confidence: { type: 'NUMBER' },
        reason: { type: 'STRING' },
        language: { type: 'STRING' }
      },
      required: ['team','intent','urgency','complaint_flag','confidence','reason','language']
    }
  }
}) }}"""

OLLAMA_BODY = r"""={{ JSON.stringify({
  model: $('Normalize input').item.json.ollama_model,
  stream: false,
  options: { temperature: 0, num_ctx: 4096 },
  format: {
    type: 'object',
    properties: {
      team: { type: 'string', enum: $('Normalize input').item.json.teams },
      secondary_team: { type: 'string' },
      intent: { type: 'string' },
      urgency: { type: 'string', enum: ['low','medium','high'] },
      complaint_flag: { type: 'boolean' },
      confidence: { type: 'number' },
      reason: { type: 'string' },
      language: { type: 'string' }
    },
    required: ['team','intent','urgency','complaint_flag','confidence','reason','language']
  },
  messages: [
    { role: 'system', content: $('Normalize input').item.json.system_prompt },
    { role: 'user', content: 'Triage this email:\n\n' + $('Normalize input').item.json.email_text }
  ]
}) }}"""

PARSE_JS = r"""// Parse and validate model output (Gemini or Ollama), apply complaint safety net, set status.
const COMPLAINT_RX = /(third time|second time|still (have not|haven't)|no one (has )?(called|responded|replied)|unacceptable|disappointed|frustrat|complain|department of insurance|insurance commissioner|regulator|attorney|lawyer|better business bureau|\bBBB\b|cancel my polic|switch(ing)? (insurers|companies)|ridiculous|terrible service|queja|reclamo)/i;
const out = [];
const src = $('Normalize input').all();
$input.all().forEach((it, i) => {
  const base = src[i] ? src[i].json : $('Normalize input').first().json;
  const r = it.json;
  let raw = '', providerUsed = base.provider, parsed = null, parseError = '';
  if (r.candidates) { providerUsed = 'gemini'; raw = r.candidates?.[0]?.content?.parts?.map(p => p.text || '').join('') || ''; }
  else if (r.message) { providerUsed = 'ollama'; raw = r.message.content || ''; }
  else { raw = JSON.stringify(r); }
  try {
    const cleaned = raw.replace(/^```(json)?/i, '').replace(/```$/, '').trim();
    parsed = JSON.parse(cleaned);
  } catch (e) { parseError = 'JSON parse failed: ' + e.message; }
  const teams = base.teams;
  let team = parsed?.team, conf = Number(parsed?.confidence);
  const problems = [];
  if (parsed) {
    if (!teams.includes(team)) problems.push('team not in list: ' + team);
    if (isNaN(conf) || conf < 0 || conf > 1) { problems.push('confidence invalid'); conf = 0; }
  }
  const ruleComplaint = COMPLAINT_RX.test(base.subject + ' ' + base.body);
  const complaint = Boolean(parsed?.complaint_flag) || ruleComplaint;
  if (complaint) team = 'Complaints Unit';
  let status;
  if (!parsed || problems.length) status = 'NEEDS_REVIEW';
  else if (complaint) status = 'COMPLAINT';
  else if (conf < (providerUsed === 'gemini' ? base.gemini_threshold : base.ollama_threshold)) status = 'NEEDS_REVIEW';
  else status = 'AUTO_ROUTED';
  out.push({ json: {
    item_id: base.item_id, received_at: base.received_at, source: base.source,
    sender: base.sender, subject: base.subject, body: base.body,
    provider_used: providerUsed, model: providerUsed === 'gemini' ? base.gemini_model : base.ollama_model,
    ai_team: parsed?.team || '', secondary_team: (base.teams.includes(parsed?.secondary_team) && parsed?.secondary_team !== team) ? parsed.secondary_team : '',
    proposed_team: team || 'General Inquiries', intent: parsed?.intent || '',
    urgency: complaint ? 'high' : (parsed?.urgency || 'medium'),
    ai_complaint_flag: Boolean(parsed?.complaint_flag), rule_complaint_flag: ruleComplaint,
    complaint_flag: complaint, confidence: conf || 0, reason: parsed?.reason || '',
    language: parsed?.language || '', status,
    validation_notes: [parseError, ...problems].filter(Boolean).join('; '),
    raw_model_output: raw.slice(0, 2000),
    expected_team: base.expected_team, expected_complaint: base.expected_complaint,
    processed_at: $now.toISO()
  }});
});
return out;
"""

MANUAL_JS = r"""// AI disabled or AI service unavailable (both Gemini and Ollama failed): item is NEVER dropped.
const src = $('Normalize input').all();
return src.map(s => ({ json: {
  item_id: s.json.item_id, received_at: s.json.received_at, source: s.json.source,
  sender: s.json.sender, subject: s.json.subject, body: s.json.body,
  provider_used: 'none', model: '', ai_team: '', secondary_team: '', proposed_team: '',
  intent: '', urgency: 'medium', ai_complaint_flag: false, rule_complaint_flag: false,
  complaint_flag: false, confidence: 0, reason: '',
  language: '', status: s.json.ai_enabled ? 'AI_UNAVAILABLE_MANUAL' : 'AI_OFF_MANUAL',
  validation_notes: s.json.ai_enabled ? 'Gemini and Ollama both failed; see execution log' : 'AI step switched off in CONFIG',
  raw_model_output: '', expected_team: s.json.expected_team, expected_complaint: s.json.expected_complaint,
  processed_at: $now.toISO()
}}));
"""

LOG_JS = r"""// Append every item to the audit log (JSON Lines) and a CSV copy. Requires NODE_FUNCTION_ALLOW_BUILTIN=fs,path
const fs = require('fs');
const dir = '/files/logs';
fs.mkdirSync(dir, { recursive: true });
const cols = ['item_id','received_at','processed_at','source','provider_used','model','status','destination','proposed_team','secondary_team','intent','urgency','complaint_flag','ai_complaint_flag','rule_complaint_flag','confidence','reason','language','validation_notes','sender','subject','expected_team','expected_complaint'];
const csvPath = dir + '/triage_log.csv';
if (!fs.existsSync(csvPath)) fs.appendFileSync(csvPath, cols.join(',') + '\n');
const esc = v => '"' + String(v ?? '').replace(/"/g, '""').replace(/\r?\n/g, ' ') + '"';
for (const it of $input.all()) {
  fs.appendFileSync(dir + '/triage_log.jsonl', JSON.stringify(it.json) + '\n');
  fs.appendFileSync(csvPath, cols.map(c => esc(it.json[c])).join(',') + '\n');
}
return $input.all();
"""

def triage():
    N=[]
    N.append(node("Email intake form","n8n-nodes-base.formTrigger",2.2,[0,0],{
        "formTitle":"Harbor Ridge – Email Triage (FICTIONAL TRAINING DATA ONLY)",
        "formDescription":"Paste one fictional customer service email. Do not enter real names, policy numbers or addresses.",
        "formFields":{"values":[
            {"fieldLabel":"Sender name","requiredField":True},
            {"fieldLabel":"Subject","requiredField":True},
            {"fieldLabel":"Email body","fieldType":"textarea","requiredField":True}]},
        "responseMode":"lastNode","options":{}},webhookId=nid()))
    N.append(node("From batch runner","n8n-nodes-base.executeWorkflowTrigger",1.1,[0,220],{"inputSource":"passthrough"}))
    N.append(node("Normalize input","n8n-nodes-base.code",2,[240,100],{"jsCode":NORMALIZE_JS}))
    N.append(node("AI enabled?","n8n-nodes-base.if",2.2,[460,100],{"conditions":{"options":{"caseSensitive":True,"leftValue":"","typeValidation":"loose","version":2},
        "conditions":[{"id":nid(),"leftValue":"={{ $json.ai_enabled }}","rightValue":True,"operator":{"type":"boolean","operation":"true","singleValue":True}}],"combinator":"and"},"options":{}}))
    N.append(node("Provider is Gemini?","n8n-nodes-base.if",2.2,[680,0],{"conditions":{"options":{"caseSensitive":True,"leftValue":"","typeValidation":"loose","version":2},
        "conditions":[{"id":nid(),"leftValue":"={{ $json.provider }}","rightValue":"gemini","operator":{"type":"string","operation":"equals"}}],"combinator":"and"},"options":{}}))
    N.append(node("Gemini – classify","n8n-nodes-base.httpRequest",4.2,[920,-100],{
        "method":"POST",
        "url":"=https://generativelanguage.googleapis.com/v1beta/models/{{ $json.gemini_model }}:generateContent",
        "authentication":"genericCredentialType","genericAuthType":"httpHeaderAuth",
        "sendBody":True,"specifyBody":"json","jsonBody":GEMINI_BODY,"options":{"timeout":60000}},
        credentials={"httpHeaderAuth":{"id":"REPLACE_ME","name":"Gemini API key"}},
        retryOnFail=True,maxTries=3,waitBetweenTries=5000,onError="continueErrorOutput"))
    N.append(node("Ollama – classify (backup)","n8n-nodes-base.httpRequest",4.2,[1160,80],{
        "method":"POST","url":"={{ $('Normalize input').item.json.ollama_url }}/api/chat",
        "sendBody":True,"specifyBody":"json","jsonBody":OLLAMA_BODY,"options":{"timeout":180000}},
        retryOnFail=True,maxTries=2,waitBetweenTries=3000,onError="continueErrorOutput"))
    N.append(node("Parse and validate","n8n-nodes-base.code",2,[1400,-60],{"jsCode":PARSE_JS}))
    N.append(node("Manual queue item","n8n-nodes-base.code",2,[1400,260],{"jsCode":MANUAL_JS}))
    rules=[]
    for key,label in [("COMPLAINT","Complaints Unit"),("NEEDS_REVIEW","Review queue"),("AUTO_ROUTED","Team queue")]:
        rules.append({"conditions":{"options":{"caseSensitive":True,"leftValue":"","typeValidation":"strict","version":2},
            "conditions":[{"id":nid(),"leftValue":"={{ $json.status }}","rightValue":key,"operator":{"type":"string","operation":"equals"}}],"combinator":"and"},
            "renameOutput":True,"outputKey":label})
    N.append(node("Route by status","n8n-nodes-base.switch",3.2,[1640,-60],{"rules":{"values":rules},"options":{"fallbackOutput":1}}))
    def setdest(name,pos,dest):
        return node(name,"n8n-nodes-base.set",3.4,pos,{"mode":"manual","includeOtherFields":True,"assignments":{"assignments":[
            {"id":nid(),"name":"destination","value":dest,"type":"string"}]},"options":{}})
    N.append(setdest("To Complaints Unit (same day)",[1880,-240],"Complaints Unit – same-business-day log"))
    N.append(setdest("To human review queue",[1880,-60],"Human review queue"))
    N.append(setdest("To team queue",[1880,120],"={{ 'Team queue: ' + $json.proposed_team }}"))
    N.append(setdest("To manual queue",[1880,300],"Manual queue (no AI)"))
    N.append(node("Write audit log","n8n-nodes-base.code",2,[2120,0],{"jsCode":LOG_JS}))
    c=conn(("Email intake form",0,"Normalize input"),("From batch runner",0,"Normalize input"),
        ("Normalize input",0,"AI enabled?"),("AI enabled?",0,"Provider is Gemini?"),("AI enabled?",1,"Manual queue item"),
        ("Provider is Gemini?",0,"Gemini – classify"),("Provider is Gemini?",1,"Ollama – classify (backup)"),
        ("Gemini – classify",0,"Parse and validate"),("Gemini – classify",1,"Ollama – classify (backup)"),
        ("Ollama – classify (backup)",0,"Parse and validate"),("Ollama – classify (backup)",1,"Manual queue item"),
        ("Parse and validate",0,"Route by status"),
        ("Route by status",0,"To Complaints Unit (same day)"),("Route by status",1,"To human review queue"),("Route by status",2,"To team queue"),
        ("Manual queue item",0,"To manual queue"),
        ("To Complaints Unit (same day)",0,"Write audit log"),("To human review queue",0,"Write audit log"),
        ("To team queue",0,"Write audit log"),("To manual queue",0,"Write audit log"))
    s={"executionOrder":"v1","timezone":"America/Chicago","saveManualExecutions":True,"saveDataSuccessExecution":"all","saveDataErrorExecution":"all","errorWorkflow":"REPLACE_WITH_WF04_ID"}
    return wf("HR-01 Email Triage (Gemini primary, Ollama backup)",N,c,s)

QUEUE_JS = r"""const fs = require('fs');
const read = p => fs.existsSync(p) ? fs.readFileSync(p,'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)) : [];
const log = read('/files/logs/triage_log.jsonl');
const dec = read('/files/logs/review_decisions.jsonl');
const decided = new Set(dec.map(d => d.item_id));
const pending = log.filter(r => r.status !== 'AUTO_ROUTED' && !decided.has(r.item_id));
const recent = log.slice(-15).reverse();
const e = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const row = r => `<tr><td>${e(r.item_id)}</td><td>${e(r.status)}</td><td>${e(r.proposed_team)}</td><td>${r.complaint_flag?'YES':''}</td><td>${Number(r.confidence).toFixed(2)}</td><td>${e(r.subject)}</td><td>${e(r.reason)}</td><td>${e(r.provider_used)}</td><td>${e(r.processed_at)}</td></tr>`;
const head = '<tr><th>Item</th><th>Status</th><th>Proposed team</th><th>Complaint</th><th>Conf.</th><th>Subject</th><th>AI reason</th><th>Model</th><th>Processed</th></tr>';
const html = `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="20"><title>Review queue</title>
<style>body{font-family:Arial;margin:20px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:4px;font-size:13px}th{background:#1f3864;color:#fff}</style></head><body>
<h2>Harbor Ridge – Review queue (FICTIONAL TRAINING DATA)</h2>
<p>${pending.length} item(s) waiting for a person. Record a decision in the <b>Review decision</b> form.</p>
<table>${head}${pending.map(row).join('')}</table>
<h3>Last 15 items processed</h3><table>${head}${recent.map(row).join('')}</table>
<h3>Last 10 reviewer decisions</h3><table><tr><th>Item</th><th>Decision</th><th>Final team</th><th>Complaint</th><th>Reviewer</th><th>Reason</th><th>Time</th></tr>
${dec.slice(-10).reverse().map(d=>`<tr><td>${e(d.item_id)}</td><td>${e(d.decision)}</td><td>${e(d.final_team)}</td><td>${e(d.final_complaint)}</td><td>${e(d.reviewer)}</td><td>${e(d.reason)}</td><td>${e(d.decided_at)}</td></tr>`).join('')}</table>
</body></html>`;
return [{ json: { html } }];
"""

DECISION_JS = r"""const fs = require('fs');
const j = $input.first().json;
const id = (j['Item ID'] || '').trim();
const decision = j['Decision'];
const corrected = j['Corrected team (only if Correct)'] || '';
const reason = (j['Reason'] || '').trim();
const reviewer = (j['Reviewer role/initials'] || '').trim();
const lines = fs.existsSync('/files/logs/triage_log.jsonl') ? fs.readFileSync('/files/logs/triage_log.jsonl','utf8').split('\n').filter(Boolean).map(l=>JSON.parse(l)) : [];
const item = lines.reverse().find(r => r.item_id === id);
if (!item) throw new Error('Item ID not found in audit log: ' + id);
if (decision === 'Correct' && !corrected) throw new Error('Choose the corrected team.');
if (decision !== 'Accept' && !reason) throw new Error('A reason is required to correct or reject.');
const final_team = decision === 'Accept' ? item.proposed_team : decision === 'Correct' ? corrected : 'Returned to manual sorting';
const rec = { item_id: id, decision, ai_proposed_team: item.proposed_team, final_team,
  final_complaint: j['Is this a complaint?'] || (item.complaint_flag ? 'Yes' : 'No'),
  reason, reviewer, decided_at: $now.toISO(), ai_status: item.status, ai_confidence: item.confidence };
fs.mkdirSync('/files/logs', { recursive: true });
fs.appendFileSync('/files/logs/review_decisions.jsonl', JSON.stringify(rec) + '\n');
return [{ json: rec }];
"""

def review():
    teams=['Claims','Billing and Payments','Policy Service','New Business and Underwriting','Agent Services','Complaints Unit','General Inquiries']
    N=[]
    N.append(node("GET /review-queue","n8n-nodes-base.webhook",2,[0,0],{"httpMethod":"GET","path":"review-queue","responseMode":"responseNode","options":{}},webhookId=nid()))
    N.append(node("Build queue page","n8n-nodes-base.code",2,[240,0],{"jsCode":QUEUE_JS}))
    N.append(node("Return page","n8n-nodes-base.respondToWebhook",1.1,[480,0],{"respondWith":"text","responseBody":"={{ $json.html }}",
        "options":{"responseHeaders":{"entries":[{"name":"Content-Type","value":"text/html; charset=utf-8"}]}}}))
    N.append(node("Review decision form","n8n-nodes-base.formTrigger",2.2,[0,240],{
        "formTitle":"Harbor Ridge – Review decision","formDescription":"Accept, correct or reject the AI routing proposal. Every decision is recorded with your role and time.",
        "formFields":{"values":[
            {"fieldLabel":"Item ID","requiredField":True},
            {"fieldLabel":"Decision","fieldType":"dropdown","fieldOptions":{"values":[{"option":"Accept"},{"option":"Correct"},{"option":"Reject"}]},"requiredField":True},
            {"fieldLabel":"Corrected team (only if Correct)","fieldType":"dropdown","fieldOptions":{"values":[{"option":t} for t in teams]}},
            {"fieldLabel":"Is this a complaint?","fieldType":"dropdown","fieldOptions":{"values":[{"option":"Yes"},{"option":"No"}]},"requiredField":True},
            {"fieldLabel":"Reason","fieldType":"textarea"},
            {"fieldLabel":"Reviewer role/initials","requiredField":True}]},
        "responseMode":"lastNode","options":{}},webhookId=nid()))
    N.append(node("Validate and record decision","n8n-nodes-base.code",2,[240,240],{"jsCode":DECISION_JS}))
    c=conn(("GET /review-queue",0,"Build queue page"),("Build queue page",0,"Return page"),("Review decision form",0,"Validate and record decision"))
    return wf("HR-02 Human Review Queue and Decisions",N,c)

LOADCSV_JS = r"""// Reads the labelled fictional test set. Columns: item_id,sender,subject,body,expected_team,expected_complaint
const fs = require('fs');
const text = fs.readFileSync('/files/testset/test_emails.csv', 'utf8');
function parse(t){const rows=[];let r=[],f='',q=false;for(let i=0;i<t.length;i++){const c=t[i];
 if(q){if(c=='"'&&t[i+1]=='"'){f+='"';i++;}else if(c=='"')q=false;else f+=c;}
 else if(c=='"')q=true;else if(c==','){r.push(f);f='';}else if(c=='\n'){r.push(f);rows.push(r);r=[];f='';}else if(c!='\r')f+=c;}
 if(f||r.length){r.push(f);rows.push(r);}return rows;}
const rows = parse(text).filter(r => r.length > 1);
const h = rows.shift();
return rows.map(r => ({ json: Object.fromEntries(h.map((k,i)=>[k.trim(), r[i]])) }));
"""
SCORE_JS = r"""// Scores the run against the labels and writes a results file traceable to the audit log.
const fs = require('fs');
const items = $input.all().map(i => i.json);
const scored = items.filter(r => r.expected_team);
const ok = scored.filter(r => r.proposed_team === r.expected_team).length;
const autoItems = scored.filter(r => r.status === 'AUTO_ROUTED');
const autoOk = autoItems.filter(r => r.proposed_team === r.expected_team).length;
const compl = scored.filter(r => String(r.expected_complaint).toLowerCase() === 'yes');
const complCaught = compl.filter(r => r.complaint_flag).length;
const falseCompl = scored.filter(r => String(r.expected_complaint).toLowerCase() !== 'yes' && r.complaint_flag).length;
const byStatus = items.reduce((a,r)=>(a[r.status]=(a[r.status]||0)+1,a),{});
const res = {
  run_at: $now.toISO(), items: items.length, labelled: scored.length,
  routing_accuracy: scored.length ? +(ok/scored.length).toFixed(3) : null,
  misroute_rate: scored.length ? +(1-ok/scored.length).toFixed(3) : null,
  baseline_misroute_rate: 0.30,
  auto_routed_share: scored.length ? +(autoItems.length/scored.length).toFixed(3) : null,
  auto_routed_accuracy: autoItems.length ? +(autoOk/autoItems.length).toFixed(3) : null,
  complaint_recall: compl.length ? +(complCaught/compl.length).toFixed(3) : null,
  complaints_missed: compl.filter(r=>!r.complaint_flag).map(r=>r.item_id),
  false_complaint_flags: falseCompl, by_status: byStatus,
  errors: scored.filter(r => r.proposed_team !== r.expected_team).map(r => ({ item_id: r.item_id, expected: r.expected_team, got: r.proposed_team, status: r.status }))
};
fs.mkdirSync('/files/results', { recursive: true });
fs.writeFileSync('/files/results/test_results_' + $now.toFormat('yyyyMMdd_HHmmss') + '.json', JSON.stringify(res, null, 2));
return [{ json: res }];
"""
def batch():
    N=[]
    N.append(node("Run test set","n8n-nodes-base.manualTrigger",1,[0,0],{}))
    N.append(node("Load labelled test set","n8n-nodes-base.code",2,[220,0],{"jsCode":LOADCSV_JS}))
    N.append(node("One at a time","n8n-nodes-base.splitInBatches",3,[440,0],{"batchSize":1,"options":{}}))
    N.append(node("Run HR-01 triage","n8n-nodes-base.executeWorkflow",1.2,[680,80],{"source":"database",
        "workflowId":{"__rl":True,"mode":"id","value":"REPLACE_WITH_WF01_ID"},"mode":"once","options":{"waitForSubWorkflow":True}}))
    N.append(node("Throttle (stay under free-tier RPM)","n8n-nodes-base.wait",1.1,[900,80],{"resume":"timeInterval","amount":8,"unit":"seconds"},webhookId=nid()))
    N.append(node("Score results","n8n-nodes-base.code",2,[680,-120],{"jsCode":SCORE_JS}))
    c=conn(("Run test set",0,"Load labelled test set"),("Load labelled test set",0,"One at a time"),
        ("One at a time",0,"Score results"),("One at a time",1,"Run HR-01 triage"),
        ("Run HR-01 triage",0,"Throttle (stay under free-tier RPM)"),("Throttle (stay under free-tier RPM)",0,"One at a time"))
    return wf("HR-03 Batch Test Runner and Scoring",N,c)

ERR_JS = r"""// Any unhandled failure in HR-01 lands here: logged to the manual queue so nothing is dropped.
const fs = require('fs');
const j = $input.first().json;
const rec = { logged_at: $now.toISO(), status: 'WORKFLOW_ERROR_MANUAL',
  workflow: j.workflow?.name, execution_id: j.execution?.id, execution_url: j.execution?.url,
  failed_node: j.execution?.lastNodeExecuted, error: j.execution?.error?.message };
fs.mkdirSync('/files/logs', { recursive: true });
fs.appendFileSync('/files/logs/manual_queue_errors.jsonl', JSON.stringify(rec) + '\n');
return [{ json: rec }];
"""
def errwf():
    N=[node("On workflow error","n8n-nodes-base.errorTrigger",1,[0,0],{}),
       node("Log to manual queue","n8n-nodes-base.code",2,[240,0],{"jsCode":ERR_JS})]
    return wf("HR-04 Error Handler (manual queue)",N,conn(("On workflow error",0,"Log to manual queue")))

FNOL_PREP_JS = r"""const it = $input.first();
const key = Object.keys(it.binary || {})[0];
if (!key) throw new Error('No file uploaded');
const buf = await this.helpers.getBinaryDataBuffer(0, key);
const mime = it.binary[key].mimeType || 'application/pdf';
return [{ json: { claim_ref: 'FNOL-' + $now.toFormat('yyyyMMdd-HHmmss'), file_name: it.binary[key].fileName, mime, b64: buf.toString('base64') } }];
"""
FNOL_BODY = r"""={{ JSON.stringify({
  systemInstruction: { parts: [{ text: 'You extract fields from a FICTIONAL first notice of loss (FNOL) form for Harbor Ridge Mutual Insurance. Extract only what is written. If a field is missing or unreadable return an empty value and confidence 0. Never assess coverage, liability, fault, approval or denial.' }] },
  contents: [{ role: 'user', parts: [ { inline_data: { mime_type: $json.mime, data: $json.b64 } }, { text: 'Extract the FNOL fields.' } ] }],
  generationConfig: { temperature: 0, responseMimeType: 'application/json',
    responseSchema: { type: 'OBJECT', properties: { fields: { type: 'ARRAY', items: { type: 'OBJECT', properties: {
      name: { type: 'STRING', enum: ['policy_number','insured_name','date_of_loss','time_of_loss','loss_location','loss_type','description','vehicle_or_property','injuries_reported','police_report_number','reporting_agent','contact_phone'] },
      value: { type: 'STRING' }, confidence: { type: 'NUMBER' } }, required: ['name','value','confidence'] } },
      legibility: { type: 'STRING', enum: ['good','fair','poor'] } }, required: ['fields','legibility'] } }
}) }}"""
FNOL_LOG_JS = r"""const fs = require('fs');
const prep = $('Prepare file').first().json;
const r = $input.first().json;
let parsed = null, err = '';
try { parsed = JSON.parse(r.candidates?.[0]?.content?.parts?.[0]?.text || ''); } catch (e) { err = e.message; }
const fields = parsed?.fields || [];
const low = fields.filter(f => Number(f.confidence) < 0.8 || !f.value).map(f => f.name);
const rec = { claim_ref: prep.claim_ref, file_name: prep.file_name, extracted_at: $now.toISO(),
  status: 'ADJUSTER_REVIEW', legibility: parsed?.legibility || 'unknown', fields, fields_to_check: low,
  note: err ? 'Extraction failed: ' + err + ' – enter manually' : 'Adjuster confirms or corrects every field. No coverage or denial output.' };
fs.mkdirSync('/files/logs', { recursive: true });
fs.appendFileSync('/files/logs/fnol_extractions.jsonl', JSON.stringify(rec) + '\n');
return [{ json: rec }];
"""
def fnol():
    N=[node("FNOL upload form","n8n-nodes-base.formTrigger",2.2,[0,0],{"formTitle":"FNOL extraction (stretch) – FICTIONAL FORMS ONLY",
        "formFields":{"values":[{"fieldLabel":"FNOL file","fieldType":"file","multipleFiles":False,"acceptFileTypes":".pdf,.png,.jpg,.jpeg","requiredField":True}]},
        "responseMode":"lastNode","options":{}},webhookId=nid()),
       node("Prepare file","n8n-nodes-base.code",2,[240,0],{"jsCode":FNOL_PREP_JS}),
       node("Gemini – extract fields","n8n-nodes-base.httpRequest",4.2,[480,0],{"method":"POST",
        "url":"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent",
        "authentication":"genericCredentialType","genericAuthType":"httpHeaderAuth","sendBody":True,"specifyBody":"json","jsonBody":FNOL_BODY,"options":{"timeout":120000}},
        credentials={"httpHeaderAuth":{"id":"REPLACE_ME","name":"Gemini API key"}},retryOnFail=True,maxTries=3,waitBetweenTries=5000),
       node("Log for adjuster review","n8n-nodes-base.code",2,[720,0],{"jsCode":FNOL_LOG_JS})]
    return wf("HR-05 FNOL Field Extraction (stretch goal)",N,conn(("FNOL upload form",0,"Prepare file"),("Prepare file",0,"Gemini – extract fields"),("Gemini – extract fields",0,"Log for adjuster review")))

files={"HR-01_email_triage.json":triage(),"HR-02_review_queue.json":review(),"HR-03_batch_test_runner.json":batch(),"HR-04_error_handler.json":errwf(),"HR-05_fnol_extraction_stretch.json":fnol()}
for f,w in files.items():
    json.dump(w,open(f,"w"),indent=2,ensure_ascii=False)
