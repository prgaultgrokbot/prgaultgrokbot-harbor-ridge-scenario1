// Scores the run against the labels and writes a results file traceable to the audit log.
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
