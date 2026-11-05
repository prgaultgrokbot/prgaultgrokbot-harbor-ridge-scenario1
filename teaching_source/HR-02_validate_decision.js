const fs = require('fs');
const j = $input.first().json;
const id = (j['Item ID'] || '').trim();
const decision = {'Accept (assignment accurate)': 'Accept', 'Update team (assignment inaccurate)': 'Update', 'Reject': 'Reject'}[j['Decision']];
if (!decision) throw new Error('Choose a valid decision.');
const corrected = j['Updated team (only when assignment was inaccurate)'] || '';
const reason = (j['Reason'] || '').trim();
const reviewer = (j['Reviewer role/initials'] || '').trim();
const lines = fs.existsSync('/files/logs/triage_log.jsonl') ? fs.readFileSync('/files/logs/triage_log.jsonl','utf8').split('\n').filter(Boolean).map(l=>JSON.parse(l)) : [];
const item = lines.reverse().find(r => r.item_id === id);
if (!item) throw new Error('Item ID not found in audit log: ' + id);
if (decision === 'Update' && !['Claims', 'Billing and Payments', 'Policy Service', 'New Business and Underwriting', 'Agent Services', 'Complaints Unit', 'General Inquiries'].includes(corrected)) throw new Error('Choose the updated team for the inaccurate assignment.');
if (decision !== 'Accept' && !reason) throw new Error('A reason is required to update the team or reject.');
const final_team = decision === 'Accept' ? item.proposed_team : decision === 'Update' ? corrected : 'Returned to manual sorting';
const rec = { item_id: id, decision, ai_proposed_team: item.proposed_team, final_team,
  final_complaint: j['Is this a complaint?'] || (item.complaint_flag ? 'Yes' : 'No'),
  reason, reviewer, decided_at: $now.toISO(), ai_status: item.status, ai_confidence: item.confidence };
fs.mkdirSync('/files/logs', { recursive: true });
fs.appendFileSync('/files/logs/review_decisions.jsonl', JSON.stringify(rec) + '\n');
return [{ json: rec }];
