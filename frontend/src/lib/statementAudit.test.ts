import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parse1CStatement } from '../v2/statement';
function doc(date:string,amount='100',number='1') { return `СекцияДокумент=Платежное поручение\nНомер=${number}\nДата=${date}\nСумма=${amount}\nПлательщик=Компания\nПлательщикСчет=OWN\nПолучатель=Поставщик\nПолучательСчет=OTHER\nПолучательИНН=anon\nНазначениеПлатежа=Оплата\nКонецДокумента`; }
const header='1CClientBankExchange\nРасчСчет=OWN\nКонечныйОстаток=900\n';
test('1C preview reconstructs distinct daily balances in chronological order',()=>{
 const preview=parse1CStatement(header+doc('02.10.2026','50','2')+'\n'+doc('01.10.2026','100','1'));
 assert.deepEqual(preview.rows.map(r=>[r[0],r[6]]),[['2026-10-02','900.00'],['2026-10-01','950.00']]);
});
test('1C repeats actual end-of-day balance for same-day documents',()=>{
 const preview=parse1CStatement(header+doc('01.10.2026','100','1')+'\n'+doc('01.10.2026','50','2'));
 assert.deepEqual(preview.rows.map(r=>r[6]),['900.00','900.00']);
});
test('1C never invents zero closing balance or silently drops malformed documents',()=>{
 assert.throws(()=>parse1CStatement('1CClientBankExchange\nРасчСчет=OWN\n'+doc('01.10.2026')),/остаток/i);
 assert.throws(()=>parse1CStatement('1CClientBankExchange\nКонечныйОстаток=\n'+doc('01.10.2026')),/остаток/i);
 assert.throws(()=>parse1CStatement(header+doc('01.10.2026')+'\n'+doc('','100','2')),/документ/i);
 assert.throws(()=>parse1CStatement(header+doc('01.10.2026')+'\nСекцияДокумент=Платежное поручение\nДата=02.10.2026'),/документ/i);
});
