// Test funcțional Zion Stream — rulează logica JS reală cu DOM/fetch simulate
const fs = require('fs');
const appJs = fs.readFileSync(process.argv[2] || 'zion-stream.html', 'utf8')
  .match(/<script>([\s\S]*)<\/script>/)[1];

// ---- stubs ----
function el(tag){
  const e = {
    tag, style:{}, children:[], value:'', textContent:'', placeholder:'', selected:false,
    classList:{ _s:new Set(), add(c){this._s.add(c);}, remove(c){this._s.delete(c);}, toggle(c,v){ v?this._s.add(c):this._s.delete(c);}, contains(c){return this._s.has(c);} },
    _innerHTML:'',
    set innerHTML(v){ this._innerHTML=v; this.children=[]; },
    get innerHTML(){ return this._innerHTML; },
    appendChild(c){ this.children.push(c); return c; },
    querySelector(){ return el('q'); },
    querySelectorAll(){ if(!this._qsa) this._qsa=[el('b'),el('b'),el('b'),el('b'),el('b')]; return this._qsa; },
  };
  return e;
}
const ids = {};
const document = {
  getElementById(id){ if(!ids[id]) ids[id]=el(id); return ids[id]; },
  createElement(t){ return el(t); },
};
const store = new Map();
const localStorage = {
  getItem:k=>store.has(k)?store.get(k):null,
  setItem:(k,v)=>store.set(k,String(v)),
  removeItem:k=>store.delete(k),
};
const location = { protocol:'file:', origin:'' };
const prompt = () => promptValue; let promptValue = 'x';
const confirm = () => true;

// fetch simulat: înregistrează comenzile către streamer, servește serverul local mock
const cmds = [];
let resolveDelay = 0;
const fetch = async (url, opts) => {
  if (url.includes('/httpapi.asp')) { cmds.push(decodeURIComponent(url.split('command=')[1])); return { ok:true, text:async()=>'', }; }
  if (url.includes('/api/cmd?')) {
    const c = decodeURIComponent(url.split('&c=')[1]);
    cmds.push(c);
    return { ok:true, text:async()=> c.startsWith('get') ? '{"status":"play","vol":"40","DeviceName":"ZionView"}' : 'OK' };
  }
  if (url.includes('/api/ping')) return { ok:true, json:async()=>({ok:true, lan:'http://192.168.2.10:8321'}) };
  if (url.includes('/api/resolve/')) {
    await new Promise(r=>setTimeout(r, resolveDelay));
    const id = url.split('/api/resolve/')[1];
    return { ok:true, json:async()=>({url:'http://audio/'+id+'.m4a', duration:100}) };
  }
  if (url.includes('/api/search')) return { ok:true, json:async()=>[
    {id:'AAAAAAAAAAA', title:'Piesa A <img src=x onerror=alert(1)>', artist:'Artist <b>X</b>', duration:180, thumb:'http://t/a.jpg'},
    {id:'BBBBBBBBBBB', title:'Piesa B', artist:'Artist Y', duration:200, thumb:'http://t/b.jpg'},
    {id:'CCCCCCCCCCC', title:'Piesa C', artist:'Artist Z', duration:220, thumb:'http://t/c.jpg'},
  ]};
  throw new Error('rețea indisponibilă: ' + url); // instanțele piped pică în test
};

let pass=0, fail=0;
function check(name, cond){ if(cond){pass++; console.log('  PASS  '+name);} else {fail++; console.log('  FAIL  '+name);} }
const sleep = ms => new Promise(r=>setTimeout(r,ms));

// ---- rulează aplicația + testele ----
eval(appJs + `
;(async () => {
  localStorage.setItem('localSrv','http://pc:8321');
  localStorage.setItem('arylicIp','1.2.3.4');
  ip = '1.2.3.4';

  // T1: handlerele din HTML există
  const fns = ['saveIp','testConn','saveLocalSrv','testLocalSrv','pinPiped','checkInstances','savePiped','doSearch','pasteLink','newPlaylist','clearQueue','queueToPlaylist','prevTrack','togglePause','nextTrack','toggleShuffle','toggleRepeat','setVol','closeModal','playIndex','stopPlayback'];
  check('T1 toate funcțiile există', fns.every(f => { try { return typeof eval(f)==='function'; } catch(e){ return false; } }));

  // T2: căutare prin serverul local
  document.getElementById('q').value = 'test';
  await doSearch();
  const res = document.getElementById('results').children;
  check('T2 căutarea întoarce 3 rezultate', res.length === 3);

  // T3: XSS — titlul/artistul nu ajung în innerHTML, ci în textContent
  check('T3 innerHTML fără date externe', !res[0]._innerHTML.includes('onerror=alert') && !res[0]._innerHTML.includes('<b>X</b>'));

  // T4: play din căutare — trebuie să folosească releul HTTP local (nu URL https direct)
  res[0]._qsa[0].onclick();
  await sleep(80);
  const playCmd = cmds.find(c=>c.startsWith('setPlayerCmd:play:'));
  check('T4 comanda play trimisă către streamer', !!playCmd && playCmd.includes('AAAAAAAAAAA'));
  check('T4c redarea trece prin releul HTTP local', !!playCmd && decodeURIComponent(playCmd).includes('192.168.2.10:8321/api/audio/'));
  check('T4b cur=0 și coada are 1 piesă', cur===0 && queue.length===1);

  // T5: race — două playIndex rapide => o singură comandă play (ultima câștigă)
  res[1]._qsa[1].onclick(); res[2]._qsa[1].onclick(); // +Coadă B și C
  cmds.length = 0; resolveDelay = 60;
  playIndex(1); await sleep(10); playIndex(2);
  await sleep(200); resolveDelay = 0;
  const plays = cmds.filter(c=>c.startsWith('setPlayerCmd:play:'));
  check('T5 fără redare dublă la click-uri rapide', plays.length===1 && plays[0].includes('CCCCCCCCCCC') && cur===2);

  // T6: ștergerea piesei curente oprește redarea
  cmds.length = 0;
  renderQueue();
  document.getElementById('queue').children[2]._qsa[2].onclick(); // ✕ pe piesa curentă (index 2)
  await sleep(20);
  check('T6 stop trimis + cur resetat', cmds.includes('setPlayerCmd:stop') && cur===-1 && queue.length===2);

  // T7: shuffle nu repetă piese și se termină corect
  queue = [{id:'AAAAAAAAAAA',title:'A',artist:'',duration:1},{id:'BBBBBBBBBBB',title:'B',artist:'',duration:1},{id:'CCCCCCCCCCC',title:'C',artist:'',duration:1}];
  played = new Set(); cur = -1; shuffle = true; repeat = false;
  cmds.length = 0;
  await playIndex(0); await sleep(20);
  nextTrack(); await sleep(50);
  nextTrack(); await sleep(50);
  nextTrack(); await sleep(50); // a 4-a: trebuie să se termine, nu să repete
  const shufPlays = cmds.filter(c=>c.startsWith('setPlayerCmd:play:'));
  const uniq = new Set(shufPlays.map(c=>c.slice(-15)));
  check('T7 shuffle: 3 piese, fiecare o dată, apoi stop', shufPlays.length===3 && uniq.size===3);

  // T8: repeat reia coada de la capăt
  shuffle = false; repeat = true; cur = 2; played = new Set();
  cmds.length = 0;
  nextTrack(); await sleep(50);
  check('T8 repeat reia de la prima piesă', cmds.some(c=>c.includes('AAAAAAAAAAA')));

  // T9: link cu mix automat (list=RD...) e refuzat elegant
  promptValue = 'https://youtube.com/playlist?list=RDabcdefghijk';
  await pasteLink();
  check('T9 mixurile RD refuzate cu mesaj', document.getElementById('status').textContent.includes('RD'));

  // T10: link cu piesă+list => piesa are prioritate
  promptValue = 'https://www.youtube.com/watch?v=DDDDDDDDDDD&list=PLxyzxyzxyzxy';
  const qlen = queue.length;
  await pasteLink(); await sleep(50);
  check('T10 piesa are prioritate față de playlist', queue.length===qlen+1 && queue[queue.length-1].id==='DDDDDDDDDDD');

  // T11: golește coada => stop + UI resetat
  cmds.length = 0;
  clearQueue();
  check('T11 golire coadă: stop + coadă goală', cmds.includes('setPlayerCmd:stop') && queue.length===0 && document.getElementById('np')._innerHTML.includes('Nimic'));

  console.log('\\nRezultat: ' + pass + ' PASS, ' + fail + ' FAIL');
  process.exit(fail ? 1 : 0);
})().catch(e=>{ console.error('EROARE HARNESS:', e); process.exit(2); });
`);
