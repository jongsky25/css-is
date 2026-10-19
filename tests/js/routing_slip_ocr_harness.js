const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx={Date,Set,Array,String,Number,Math,JSON,Error};vm.createContext(ctx);
vm.runInContext(fs.readFileSync('apps_script/documents_relay.gs','utf8'),ctx);
// Transcription of the visible routing-slip labels, not a claim about Google's OCR output.
const scan=`Document Tracking Information System
(DTRAK)
Effectivity: March 30, 2015
2026-000117885
ORIGINATING OFFICE: BLHSD - Health Systems Development Division (HSDD) DATE: 10/15/2026
TYPE OF DOCUMENT: Memorandum
SUBJECT: Invitation to the High-Level Universal Health Care (UHC) Summit 2026
DATE FROM TO ACTION REQUIRED DUE DATE NAME
2026-10-15 BLHSD For Signature 2026-10-15`;
let s=ctx.dmSuggest_(scan).suggestions;
assert.equal(s.type,'Memorandum');assert.equal(s.sender,'BLHSD - Health Systems Development Division (HSDD)');
assert.equal(s.subject,'Invitation to the High-Level Universal Health Care (UHC) Summit 2026');
assert.equal(s.document_date,'2026-10-15');assert.equal(s.references,'DTRAK: 2026-000117885');
assert(!s.due_date);assert(!s.direction);assert(!s.received_at);
s=ctx.dmSuggest_('TYPE OF DOCUMENT:\nMemorandum\nORIGINATING OFFICE:\nHealth Systems\nDevelopment Division\nDATE: 15 October 2026\nSUBJECT:\nInvitation to the Summit\n2026\nDeadline: October 30, 2026').suggestions;
assert.equal(s.subject,'Invitation to the Summit 2026');assert.equal(s.type,'Memorandum');assert.equal(s.sender,'Health Systems Development Division');assert.equal(s.document_date,'2026-10-15');assert.equal(s.due_date,'2026-10-30');
assert.equal(ctx.dmSuggest_('Date: 15/10/2026').suggestions.document_date,'2026-10-15');
assert(!ctx.dmSuggest_('Date: 01/02/2026').suggestions.document_date);
assert(!ctx.dmSuggest_('Date: 2026-02-30').suggestions.document_date);
assert(!ctx.dmSuggest_('Date: 10/15/2026\nDate: 10/16/2026').suggestions.document_date);
assert.equal(ctx.dmSuggest_('Please respond on or before 30 October 2026.').suggestions.due_date,'2026-10-30');
assert(!ctx.dmSuggest_('Deadline: October 30, 2026\nDeadline: November 1, 2026').suggestions.due_date);
assert(!ctx.dmSuggest_('TYPE OF DOCUMENT:\nSUBJECT: Test').suggestions.type);
assert(!ctx.dmSuggest_('Header without a subject label').suggestions.subject);
assert(!ctx.dmSuggest_(scan+'\nSUBJECT: A different enclosed letter').suggestions.subject);
assert.equal(ctx.dmSuggest_('Subject: A safe title\nFrom: Regional Office\nDeadline 2026-10-30').suggestions.due_date,'2026-10-30');
console.log('Routing slip metadata and conservative multi-page date handling passed');
