// Reads the labelled fictional test set. Columns: item_id,sender,subject,body,expected_team,expected_complaint
const fs = require('fs');
const text = fs.readFileSync('/files/testset/test_emails.csv', 'utf8');
function parse(t){const rows=[];let r=[],f='',q=false;for(let i=0;i<t.length;i++){const c=t[i];
 if(q){if(c=='"'&&t[i+1]=='"'){f+='"';i++;}else if(c=='"')q=false;else f+=c;}
 else if(c=='"')q=true;else if(c==','){r.push(f);f='';}else if(c=='\n'){r.push(f);rows.push(r);r=[];f='';}else if(c!='\r')f+=c;}
 if(f||r.length){r.push(f);rows.push(r);}return rows;}
const rows = parse(text).filter(r => r.length > 1);
const h = rows.shift();
return rows.map(r => ({ json: Object.fromEntries(h.map((k,i)=>[k.trim(), r[i]])) }));
