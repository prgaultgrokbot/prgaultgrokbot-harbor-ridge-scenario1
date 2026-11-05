Harbor Ridge Scenario 1 — how the sausage is made
=================================================

Two layers:

1) n8n workflows (the real solution interns build)
   HR-01  Email triage (Gemini primary, Ollama backup) → audit log
   HR-02  Human review queue + decision form
   HR-03  Manual "Load labelled test set" → runs all 32 emails → writes test_results_*.json
   HR-04  Error handler (nothing dropped)
   HR-05  FNOL stretch (optional)

2) Demo hub (thin Python + HTML so a client can click through it)
   server.py     serves the page on :8787 and proxies /form and /webhook to n8n :5678
   static/index.html  executive scoreboard + iframes for the live n8n forms
   /api/scoreboard    reads files/results/test_results_*.json
   /api/samples       reads files/testset/test_emails.csv

Teaching files in this folder:
  01_demo_hub_server.py
  02_demo_hub_index.html
  03_HR-01_email_triage.json
  04_HR-02_review_queue.json
  05_HR-03_batch_test_runner.json
  06_build_wf.py                  (generator that wrote the workflow JSON)
  extract_HR-02_form_fields.json  (decision form labels)
  extract_HR-02_validate.js       (records Accept / Correct / Reject)
  extract_HR-03_load_testset.js
  extract_HR-03_score_results.js  (writes the executive metrics file)

Note: Jules is updating (a) review wording so team changes only happen on an
inaccurate assignment, and (b) scoreboard to follow the latest manual test run.
