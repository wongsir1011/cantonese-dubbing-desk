#!/usr/bin/env node
/* 純邏輯回歸測試。唔使 API key、唔使瀏覽器。
   用法：node test.js
   由 index.html 直接抽出頂層函數嚟跑，所以測試永遠對住真實 code，唔會走樣。 */
const fs = require('fs');

const SRC = fs.readFileSync(__dirname + '/index.html', 'utf8').split('\n');
function grab(name) {
  const st = SRC.findIndex(l => new RegExp('^\\s*function\\s+' + name + '\\s*\\(').test(l));
  if (st < 0) throw new Error('揾唔到函數 ' + name);
  let en = st + 1;
  while (en < SRC.length && SRC[en] !== '}') en++;
  return SRC.slice(st, en + 1).join('\n');
}
function grabConst(name) {
  const l = SRC.find(x => new RegExp('^(?:const|let)\\s+' + name + '\\s*=').test(x));
  if (!l) throw new Error('揾唔到常數 ' + name);
  return l;
}
const CONSTS = ['CJK_CHAR', 'NON_CJK_LETTER', 'HAN_CHAR', 'KANA_HANGUL', 'ABBREV_END',
                'gMaxLen'];
const NEEDED = ['isCJKText', 'isChineseText', 'endsSentence', 'gvRate', 'gSplitForTTS', 'segCharLimit', 'absorbSegs', 'elGroup',
                'isBreakAt', 'wrapCJK', 'toCues', 'slotOf'];
let SNIPPETS = '';
try {
  SNIPPETS = CONSTS.map(grabConst).concat(NEEDED.map(grab)).join('\n\n');
} catch (e) { console.error('由 index.html 抽取失敗：' + e.message); process.exit(1); }
eval(SNIPPETS);   // 一次過 eval，等啲函數落喺 module scope

let pass = 0, fail = 0;
function ok(name, cond, detail) {
  if (cond) { pass++; console.log('  \x1b[32m✓\x1b[0m ' + name); }
  else { fail++; console.log('  \x1b[31m✗\x1b[0m ' + name + (detail ? '\n      ' + detail : '')); }
}
function eq(name, got, want) {
  ok(name, JSON.stringify(got) === JSON.stringify(want),
     '得到 ' + JSON.stringify(got) + '\n      預期 ' + JSON.stringify(want));
}
function group(t) { console.log('\n\x1b[1m' + t + '\x1b[0m'); }

/* 砌 ElevenLabs Scribe 逐字輸出（word / spacing 交替，係佢真實 shape） */
function mkWords(sentence, t0, spk) {
  const out = []; let t = t0;
  sentence.split(' ').forEach((w, i) => {
    if (i) out.push({ type: 'spacing', text: ' ', start: t, end: t });
    const d = 0.06 * w.length + 0.12;
    out.push({ type: 'word', text: w, start: t, end: t + d, speaker_id: spk });
    t += d;
  });
  return { words: out, end: t };
}
function mkCJK(sentence, t0, spk) {
  const out = []; let t = t0;
  for (const ch of sentence) { out.push({ type: 'word', text: ch, start: t, end: t + 0.18, speaker_id: spk }); t += 0.18; }
  return { words: out, end: t };
}

/* ─────────── Bug A：elGroup 對英文嘅斷句 ─────────── */
group('elGroup — 英文（Bug A）');
{
  const a = mkWords('The vocational rehabilitation programme has been running for about three years now and we have seen a real change in employer attitudes.', 0, 'speaker_0');
  const b = mkWords('That is interesting because most employers I speak to still worry about workplace accommodation costs.', a.end + 0.4, 'speaker_1');
  const segs = elGroup(a.words.concat(b.words));

  eq('兩句英文 → 兩段', segs.length, 2);
  ok('每段都喺句號度收', segs.every(s => /[.!?]$/.test(s.text.trim())),
     segs.map(s => JSON.stringify(s.text)).join('\n      '));
  ok('冇段落中間斷字', segs.every(s => !/[a-z]$/.test(s.text.trim().replace(/[.!?]$/, ''))
     || /\s/.test(s.text.trim())), segs.map(s => s.text).join(' | '));
  eq('講者標籤保留', segs.map(s => s.speaker), ['speaker_0', 'speaker_1']);
}

group('elGroup — 縮寫同小數唔可以當句末');
{
  const txt = 'We met Dr. Chan and the U.S. team at 9.30 and the budget rose 3.5 per cent this year.';
  const segs = elGroup(mkWords(txt, 0, 's0').words);
  eq('唔會喺 Dr. / U.S. / 9.30 / 3.5 斷開', segs.length, 1);
  eq('標點之後嘅空格保留返（唔會變 Dr.Chan）', segs[0].text.trim(), txt);
}
{
  const two = mkWords('The programme started in 2019.', 0, 's0');
  const b = mkWords('It has grown since then.', two.end + 0.1, 's0');
  const segs = elGroup(two.words.concat(b.words));
  eq('正常兩句仍然分開', segs.map(s => s.text.trim()),
     ['The programme started in 2019.', 'It has grown since then.']);
}

/* ─────────── 中文回歸：行為必須一模一樣 ─────────── */
group('elGroup — 中文回歸（唔可以改變行為）');
{
  const a = mkCJK('呢個職業復康計劃行咗三年。', 0, 's0');
  const b = mkCJK('僱主態度真係有變。', a.end + 0.2, 's0');
  const segs = elGroup(a.words.concat(b.words));
  eq('中文照舊喺句號斷', segs.map(s => s.text), ['呢個職業復康計劃行咗三年。', '僱主態度真係有變。']);
}
{
  const long = mkCJK('一二三四五六七八九十'.repeat(6), 0, 's0');   // 60 字，冇標點
  const segs = elGroup(long.words);
  ok('中文長句仍然喺 42 字硬斷', segs.length >= 2 && segs[0].text.length === 42,
     '第一段長度 ' + (segs[0] || {}).text?.length);
}

/* ─────────── Bug B：wrapCJK 拉丁文中間斷字 ─────────── */
group('wrapCJK — 英文（Bug B）');
{
  const txt = 'The vocational rehabilitation programme has been running for three years.';
  const lines = wrapCJK(txt, 20);
  const rejoined = lines.join(' ').replace(/\s+/g, ' ').trim();
  eq('換行後字詞完全冇被斬開', rejoined, txt);
  ok('行數合理（唔會一句拆成四五行）', lines.length <= 3, JSON.stringify(lines));
  ok('冇空行、冇前後多餘空格', lines.every(l => l.length > 0 && l === l.trim()),
     JSON.stringify(lines));
}
{
  const lines = wrapCJK('Supercalifragilisticexpialidocious antidisestablishmentarianism', 20);
  ok('單字長過一行都唔會死循環', lines.length >= 2 && lines.join('').length > 0,
     JSON.stringify(lines));
}

group('wrapCJK — 中文回歸（唔可以改變行為）');
{
  eq('短中文句原樣一行', wrapCJK('呢個職業復康計劃已經行咗三年。', 20),
     ['呢個職業復康計劃已經行咗三年。']);
  eq('中文標點斷句照舊', wrapCJK('第一點好緊要，第二點都好緊要，第三點最緊要。', 20),
     ['第一點好緊要，第二點都好緊要，', '第三點最緊要。']);
  eq('中文硬斷照舊', wrapCJK('一二三四五六七八九十'.repeat(3), 20),
     ['一二三四五六七八九十一二三四五六七八九十', '一二三四五六七八九十']);
}

/* ─────────── 輔助函數 ─────────── */
group('語言判斷輔助');
{
  ok('中文 → CJK', isCJKText('呢個計劃行咗三年'));
  ok('英文 → 唔係 CJK', !isCJKText('The programme has been running'));
  ok('中英夾雜以中文為主 → CJK', isCJKText('個 programme 行咗三年，好有成效'));
  ok('空字串當 CJK（保守，維持舊行為）', isCJKText(''));
  ok('日文假名 → CJK', isCJKText('これはテストです'));
  ok('韓文用空格分詞 → 唔當 CJK', !isCJKText('한국어 문장입니다'));
}
{
  ok('簡體中文 → 要簡繁轉換', isChineseText('这个计划已经三年'));
  ok('繁體中文 → 要簡繁轉換', isChineseText('呢個計劃行咗三年'));
  ok('日文（有假名）→ 唔好轉，會誤傷漢字', !isChineseText('この計画は三年間続いています'));
  ok('韓文 → 唔好轉', !isChineseText('한국어 문장입니다'));
  ok('英文 → 唔好轉', !isChineseText('The programme has been running'));
}
{
  ok('英文句號算句末', endsSentence('This is a sentence.'));
  ok('Dr. 唔算句末', !endsSentence('We met Dr.'));
  ok('小數唔算句末', !endsSentence('The rate rose 3.5'));
  ok('句末年份算句末', endsSentence('The programme started in 2019.'));
  ok('首字母縮寫唔算句末', !endsSentence('He works for the U.'));
  ok('中文句號算句末', endsSentence('呢句完咗。'));
  ok('未完成唔算句末', !endsSentence('這句還沒'));
}

/* ─────────── Chirp 3 HD 語速換算 ─────────── */
group('gvRate — mRate → Cloud TTS speakingRate');
{
  eq('正常', gvRate('0%'), 1);
  eq('慢 −10%', gvRate('-10%'), 0.9);
  eq('快 +20%', gvRate('+20%'), 1.2);
  eq('空值當正常', gvRate(''), 1);
  eq('undefined 當正常', gvRate(undefined), 1);
  // fitToSlots 最多加 50%，兩轉之後可以疊到好高，一定要夾住 API 上限
  eq('fitToSlots 加速唔會爆上限', gvRate('+50%'), 1.5);
  eq('離譜嘅快唔會超過 4', gvRate('+900%'), 4);
  eq('離譜嘅慢唔會低過 0.25', gvRate('-95%'), 0.25);
}

/* ─────────── Chirp 3 HD 斷句 ─────────── */
group('gSplitForTTS — Chirp 3 HD 要短句 + 句末標點');
{
  eq('短句原樣', gSplitForTTS('呢個計劃行咗三年。'), ['呢個計劃行咗三年。']);
  eq('冇句末標點會補返', gSplitForTTS('呢個計劃行咗三年'), ['呢個計劃行咗三年。']);
  eq('尾巴逗號換成句號', gSplitForTTS('呢個計劃行咗三年，'), ['呢個計劃行咗三年。']);
  eq('本身多句就分開', gSplitForTTS('第一句。第二句！第三句？'), ['第一句。', '第二句！', '第三句？']);
}
{
  // 長句冇句末標點——就係 Chirp 400 嘅成因
  const long = '佢哋話呢個職業復康計劃行咗三年，幫到好多服務使用者搵到工，而且僱主嘅態度都有明顯改變，真係唔容易';
  const out = gSplitForTTS(long, 45);
  ok('長句會切開', out.length > 1, JSON.stringify(out));
  ok('每段都唔超過上限', out.every(x => x.length <= 46), JSON.stringify(out.map(x => x.length)));
  ok('每段都有句末標點', out.every(x => /[。！？!?]$/.test(x)), JSON.stringify(out));
  const strip = x => x.replace(/[。，、；：！？!?,;:\s]/g, '');
  eq('切完拼返去一個字都冇少', strip(out.join('')), strip(long));
}
{
  // 完全冇標點嘅長串，唔可以死循環
  const n = gSplitForTTS('一二三四五六七八九十'.repeat(8), 45);
  ok('冇標點都切到，唔會死循環', n.length >= 2 && n.every(x => x.length <= 46),
     JSON.stringify(n.map(x => x.length)));
  ok('冇標點切完一樣有句號', n.every(x => /。$/.test(x)), JSON.stringify(n));
}
{
  eq('空字串回空陣列', gSplitForTTS(''), []);
  eq('淨係空白回空陣列', gSplitForTTS('   '), []);
  // 遞迴重試會用一半長度再切，唔可以回單一段（否則會無限遞迴）
  const t = '一二三四五六七八九十一二三四五六七八九十';
  ok('用一半長度再切一定多過一段', gSplitForTTS(t, Math.ceil(t.length / 2)).length > 1,
     JSON.stringify(gSplitForTTS(t, Math.ceil(t.length / 2))));
}

/* ─────────── toCues / slotOf 回歸 ─────────── */
group('toCues / slotOf 回歸');
{
  const cues = toCues('呢個計劃行咗三年，成效唔錯。', 0, 4, Infinity, 20, 2);
  ok('中文字幕格數合理', cues.length === 1 && cues[0].start === 0, JSON.stringify(cues));
  const ec = toCues('The vocational rehabilitation programme has been running for three years.', 0, 5, Infinity, 20, 2);
  ok('英文字幕每格文字唔會斬字', ec.every(c => !/\w-$/.test(c.text)), JSON.stringify(ec));
}
eq('slotOf 用下一句開始時間', +slotOf([{ start: 1, end: 2 }, { start: 4 }], 0, 10).toFixed(2), 2.92);

/* ─────────── absorbSegs（已知限制，P2 先處理） ─────────── */
group('absorbSegs — 現有兩講者限制（記錄用，唔係目標）');
{
  const out = [];
  absorbSegs([{ start: 0, end: 1, text: 'a', speaker: 's0' },
              { start: 1, end: 2, text: 'b', speaker: 's1' },
              { start: 2, end: 3, text: 'c', speaker: 's2' }], 0, out);
  eq('第三個講者仍然併入 B（P2 未做）', out.map(o => o.spk), ['A', 'B', 'B']);
}

console.log('\n' + (fail ? '\x1b[31m' : '\x1b[32m') + pass + ' 過 / ' + fail + ' 唔過\x1b[0m\n');
process.exit(fail ? 1 : 0);
