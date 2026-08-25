const $ = s => document.querySelector(s);
const state = { sid:null, meta:null, view:"ask", streaming:false, ctrl:null, viewingIdx:null };

function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function toast(msg){
  const t=$("#toast"); t.textContent=msg; t.style.display="block";
  clearTimeout(t._to); t._to=setTimeout(()=>t.style.display="none",4200);
}
async function api(path,opts={}){
  const r = await fetch(path,opts);
  if(!r.ok){ let e="request failed"; try{e=(await r.json()).detail||e}catch(_){} throw new Error(e);}
  return r.json();
}
function showOverlay(text){ $("#overlayText").textContent=text; $("#overlay").classList.remove("hidden"); }
function hideOverlay(){ $("#overlay").classList.add("hidden"); }

function md(src){
  let s = esc(src);
  const codes=[];
  s = s.replace(/```(\w*)\n?([\s\S]*?)```/g,(m,l,c)=>{codes.push(c.replace(/\n$/,""));return "\x00C"+(codes.length-1)+"\x00";});
  s = s.replace(/^### (.*)$/gm,"<h3>$1</h3>").replace(/^## (.*)$/gm,"<h2>$1</h2>").replace(/^# (.*)$/gm,"<h1>$1</h1>");
  s = s.replace(/`([^`\n]+)`/g,"<code>$1</code>");
  s = s.replace(/\*\*([^*\n]+)\*\*/g,"<b>$1</b>");
  s = s.replace(/^\s*[-*] (.*)$/gm,"<li>$1</li>").replace(/^\s*(\d+)\. (.*)$/gm,"<li>$2</li>");
  s = s.split(/\n{2,}/).map(b=>/^<(h\d|ul|li)/.test(b.trim())?b:(b.includes("<")?b:`<p>${b}</p>`)).join("");
  s = s.replace(/\x00C(\d+)\x00/g,(m,i)=>`<pre><code>${codes[i]}</code></pre>`);
  return s;
}

async function loadStatus(){
  try{
    const st = await api("/api/status");
    $("#statusChip").innerHTML = st.ollama
      ? `<span class="dot" style="background:var(--accent2)"></span>Ollama ready · ${esc(st.model)}`
      : `<span class="dot" style="background:var(--danger)"></span>Ollama not reachable`;
  }catch(_){
    $("#statusChip").innerHTML = `<span class="dot" style="background:var(--danger)"></span>Server offline`;
  }
}

async function loadSessions(){
  const list = await api("/api/sessions");
  const el = $("#sessionList"); el.innerHTML="";
  list.forEach(m=>{
    const d=document.createElement("div");
    d.className="sess"+(m.id===state.sid?" active":"");
    d.innerHTML=`<div style="min-width:0"><div class="nm">${esc(m.name)}</div>
      <div class="meta">${(m.docs||[]).length} doc(s)</div></div>
      <button class="del" title="Delete session (erases everything)">✕</button>`;
    d.onclick=e=>{
      if(e.target.classList.contains("del")){
        if(confirm(`Delete "${m.name}"?\n\nAll uploaded files, chat history and progress will be permanently erased.`)) delSession(m.id);
        return;
      }
      openSession(m.id);
    };
    el.appendChild(d);
  });
  return list;
}
async function delSession(id){
  await api("/api/sessions/"+id,{method:"DELETE"});
  if(state.sid===id) closeSession();
  await loadSessions();
  toast("Session deleted — memory wiped");
}
$("#wipeAll").onclick=async()=>{
  if(confirm("Delete ALL sessions and every stored document/chat permanently?")){
    await api("/api/sessions",{method:"DELETE"});
    closeSession(); await loadSessions(); toast("All data wiped");
  }
};
$("#deleteSessBtn").onclick=()=>{
  if(!state.sid)return;
  if(confirm(`Delete "${state.meta.name}"? Everything in it is erased permanently.`)) delSession(state.sid);
};
function closeSession(){
  state.sid=null;state.meta=null;state.viewingIdx=null;
  $("#sessTitle").textContent="No session selected";
  ["ask","course","topics"].forEach(v=>{const p=chatEl(v);if(p)p.innerHTML="";});
  $("#inputBar").classList.add("hidden");
  $("#uploadBtn")?.classList.add("hidden");
  $("#filesBtn").classList.add("hidden");$("#deleteSessBtn").classList.add("hidden");
  $("#lessonRows").innerHTML="";$("#courseSide").classList.add("hidden");$("#courseHero").classList.add("hidden");
  $("#topicPanelWrap").classList.add("hidden");$("#topicsHero").classList.add("hidden");
  document.querySelectorAll(".tab").forEach((t,i)=>{if(i)t.disabled=true;t.classList.toggle("active",i===0)});
  setView("ask");
}

$("#newSessionBtn").onclick=async()=>{
  const name=prompt("Name this study session:","My study session");
  if(name===null)return;
  const m=await api("/api/sessions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name})});
  await loadSessions(); openSession(m.id);
};

async function openSession(id){
  try{ state.meta=await api("/api/sessions/"+id); }catch(e){ toast(e.message); return; }
  state.sid=id; state.viewingIdx=null;
  $("#sessTitle").textContent=state.meta.name;
  $("#filesBtn").classList.remove("hidden");
  $("#deleteSessBtn").classList.remove("hidden");
  const hasDocs=(state.meta.docs||[]).length>0;
  document.querySelectorAll(".tab").forEach(t=>t.disabled=!hasDocs);
  renderAll(true);
  setView(hasDocs?"ask":"ask");
  await loadSessions();
}

function chatEl(view){ return $("#chatPane-"+view); }

function paneOfMsg(m){ return m.pane||"ask"; }

function renderAll(full){
  const hasDocs=state.sid&&(state.meta.docs||[]).length>0;
  ["ask","course","topics"].forEach(v=>{
    const pane=chatEl(v); if(!pane) return;
    pane.innerHTML="";
    (state.meta.chat||[]).filter(m=>paneOfMsg(m)===v).forEach(m=>{
      appendMsg(pane,m.role==="user"?"user":"bot",m.content,false);
    });
  });
  $("#inputBar").classList.toggle("hidden",!hasDocs);
  if(!hasDocs&&state.sid){ showUploadPrompt(); }
  else { $("#askHero").classList.add("hidden"); $("#askHero").innerHTML=""; }
  renderLessons(); renderTopics(); syncTestToggle(); updateProgress();
}

function showUploadPrompt(){
  const hero=$("#askHero");
  hero.innerHTML=`<h2>${esc(state.meta.name)}</h2>
    <p>Upload PDFs, TXT, Markdown, CSV or JSON files.<br>They are chunked and indexed locally — only inside this session.</p>
    <div class="dropzone" id="dropzone"><b>Drop files here</b> or click to browse<p>PDF · TXT · MD · CSV · JSON — multiple files supported</p></div>`;
  wireDropzone($("#dropzone"));
  hero.classList.remove("hidden");
}
function wireDropzone(dz){
  dz.onclick=()=>$("#fileInput").click();
  dz.ondragover=e=>{e.preventDefault();dz.classList.add("drag")};
  dz.ondragleave=()=>dz.classList.remove("drag");
  dz.ondrop=e=>{e.preventDefault();dz.classList.remove("drag");if(e.dataTransfer.files.length)uploadFiles(e.dataTransfer.files)};
}
$("#filesBtn").onclick=openFilesModal;

async function uploadFiles(files){
  showOverlay(`Indexing ${files.length} file(s)…`);
  const fd=new FormData();
  [...files].forEach(f=>fd.append("files",f));
  try{
    const res=await api(`/api/sessions/${state.sid}/upload`,{method:"POST",body:fd});
    const ok=res.results.filter(r=>r.ok).length, bad=res.results.filter(r=>!r.ok);
    toast(`${ok} file(s) indexed · ${res.total_chunks} chunks total`+(bad.length?` · ${bad.length} skipped`:""));
    await openSession(state.sid);
  }catch(e){toast("Upload failed: "+e.message)}
  finally{ hideOverlay(); }
}
$("#fileInput").onchange=e=>{if(e.target.files.length)uploadFiles(e.target.files);e.target.value=""};

document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>setView(t.dataset.view));
function setView(v){
  state.view=v;
  document.querySelectorAll(".tab").forEach(t=>t.classList.toggle("active",t.dataset.view===v));
  document.querySelectorAll(".pane").forEach(p=>p.classList.toggle("active",p.id==="pane-"+v));
  const inp=$("#msgInput");
  inp.placeholder = v==="course"?"Ask about the current lesson… (Enter to send)"
    : v==="topics"?"Ask about this topic… (Enter to send)":"Ask about your documents… (Enter to send)";
}

function appendMsg(pane,cls,content,live){
  const d=document.createElement("div");
  d.className="msg "+cls+(live?" streaming":"");
  d.innerHTML=cls==="user"?esc(content):md(content);
  pane.appendChild(d);pane.scrollTop=pane.scrollHeight;
  return d;
}

function updateProgress(){
  const p=state.meta?.progress||{done:0,total:0,pct:0};
  $("#progPct").textContent=`${p.done}/${p.total} lessons · ${p.pct}%`;
  $("#progFill").style.width=p.pct+"%";
}
function syncTestToggle(){
  const t=$("#testToggle");
  t.checked=!!(state.meta&&state.meta.test_enabled);
}
$("#testToggle").onchange=async e=>{
  if(!state.sid){e.target.checked=false;return;}
  try{
    const r=await api(`/api/sessions/${state.sid}/settings`,{method:"PATCH",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({test_enabled:e.target.checked})});
    state.meta.test_enabled=r.test_enabled;
    toast(r.test_enabled?"Test gate ON — pass a mini-test to unlock each next lesson":"Test gate OFF — lessons flow without tests");
    renderLessons();
  }catch(err){ e.target.checked=!e.target.checked; toast(err.message);}
};

function renderLessons(){
  const cur=state.meta?.curriculum||[];
  if(!cur.length){$("#courseSide").classList.add("hidden");$("#courseHero").classList.remove("hidden");return;}
  $("#courseHero").classList.add("hidden");$("#courseSide").classList.remove("hidden");
  updateProgress();
  const rows=$("#lessonRows");rows.innerHTML="";
  const active=cur.findIndex(l=>l.status==="active");
  state.viewingIdx=active>=0?active:null;
  cur.forEach((l,i)=>{
    const icon=l.status==="done"?"✓":l.status==="active"?"▶":"○";
    const d=document.createElement("button");
    d.className="lesson-row"+(l.status==="active"?" viewing":l.status==="done"?" done":"");
    d.innerHTML=`<span class="lt"><span class="st">${icon}</span><span>${i+1}. ${esc(l.title)}</span>${
      l.test_passed?'<span class="ttag">test ✓</span>'
      :(l.status!=="done"&&state.meta.test_enabled&&l.status==="active")?'<span class="ttag">test due</span>':""}</span>${
      l.summary?`<span class="sm">${esc(l.summary)}</span>`:""}`;
    d.onclick=()=>{ if(state.streaming)return; if(l.status==="active"){setView("course");return;} streamChat({action:"goto_lesson",lesson:i},"course"); };
    rows.appendChild(d);
  });
  const nextIdx=cur.findIndex(l=>l.status!=="done");
  const btn=$("#startNextBtn"),prev=$("#prevLessonBtn");
  btn.textContent=nextIdx===-1?"Course complete ✓":(active>=0?"Next lesson →":"Start course ▶");
  btn.disabled=false;
  prev.disabled=(active==null)||(active===0);
}
$("#startNextBtn").onclick=()=>{ if(!state.streaming) nextLessonFlow(); };
$("#prevLessonBtn").disabled=true;
$("#prevLessonBtn").onclick=()=>{
  if(state.streaming)return;
  const cur=state.meta.curriculum||[];
  const idx=state.viewingIdx??cur.findIndex(l=>l.status!=="done");
  const target=Math.max(0,(idx==null?0:idx)-1);
  if(target===idx)return;
  streamChat({action:"goto_lesson",lesson:target},"course");
};

async function nextLessonFlow(){
  const cur=state.meta?.curriculum||[];
  if(!cur.length){toast("Build the course first");return;}
  const idx=cur.findIndex(l=>l.status!=="done");
  if(idx===-1){toast("Course complete — nothing left!");return;}
  if(state.meta.test_enabled){
    try{
      const g=await api(`/api/sessions/${state.sid}/lesson/${idx}/gate`);
      if(g.required&&!g.passed){ openTest(idx,false); return; }
    }catch(e){ toast(e.message); return; }
  }
  streamChat({action:"next_lesson"},"course");
}

function renderTopics(){
  const tp=state.meta?.topics||[];
  if(!tp.length){$("#topicPanelWrap").classList.add("hidden");$("#topicsHero").classList.remove("hidden");return;}
  $("#topicsHero").classList.add("hidden");$("#topicPanelWrap").classList.remove("hidden");
  const box=$("#topicChips");box.innerHTML="";
  tp.forEach(t=>{
    const c=document.createElement("div");
    c.className="chip"+(state.currentTopic===t.title?" current":"");
    c.innerHTML=`${esc(t.title)}${t.summary?`<small title="${esc(t.summary)}">${esc(t.summary)}</small>`:""}`;
    c.onclick=()=>{
      if(state.streaming)return;
      state.currentTopic=t.title;
      box.querySelectorAll(".chip").forEach(x=>x.classList.remove("current"));
      c.classList.add("current");
      $("#topicPanel").classList.add("hidden");$("#toggleTopicsBar").textContent="▸ show document index";
      streamChat({action:"teach_topic",topic:t.title},"topics");
    };
    box.appendChild(c);
  });
}
$("#toggleTopicsBar").onclick=()=>{
  const p=$("#topicPanel");p.classList.toggle("hidden");
  $("#toggleTopicsBar").textContent=p.classList.contains("hidden")?"▸ show document index":"▾ hide document index";
};
$("#genCourseBtn").onclick=$("#genTopicsBtn").onclick=async e=>{
  const b=e.target;b.disabled=true;showOverlay("Reading your documents and designing the course…");
  try{
    const res=await api(`/api/sessions/${state.sid}/index/rebuild`,{method:"POST"});
    state.meta.curriculum=res.lessons;state.meta.topics=res.topics;
    state.meta.progress={done:0,total:res.lessons.length,pct:0};
    renderLessons();renderTopics();toast("Course plan & index ready!");
  }catch(err){toast(err.message)}
  finally{b.disabled=false;hideOverlay()}
};

function userLabelFor(p){
  if(p.action==="next_lesson")return"[Course] Next lesson please";
  if(p.action==="start_course")return"[Course] Start the course";
  if(p.action==="goto_lesson")return`[Course] Open lesson ${p.lesson+1}`;
  if(p.action==="teach_topic")return`[Topic] Teach me: ${p.topic}`;
  return p.message;
}

async function streamChat(payload,view){
  if(state.streaming)return;
  state.streaming=true; setInputs(true);
  payload.pane=view;
  const pane=chatEl(view);
  appendMsg(pane,"user",userLabelFor(payload),true);
  const bot=appendMsg(pane,"bot","",false);
  bot.innerHTML='<span class="typing"><i></i><i></i><i></i></span>';
  bot.classList.add("streaming");
  state.ctrl=new AbortController();
  let text="",err=null,aborted=false;
  try{
    const res=await fetch(`/api/chat/stream?sid=${state.sid}`,{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(payload),signal:state.ctrl.signal});
    if(!res.ok){let m="request failed";try{m=(await res.json()).detail||m}catch(_){};throw new Error(m);}
    const reader=res.body.getReader(),dec=new TextDecoder();
    while(true){
      const {done,value}=await reader.read();
      if(done)break;
      text+=dec.decode(value,{stream:true});
      const ei=text.indexOf("__ERROR__");
      if(ei>=0){err=text.slice(ei+9).trim();text=text.slice(0,ei);}
      bot.innerHTML=md(text)||'<span class="typing"><i></i><i></i><i></i></span>';
      pane.scrollTop=pane.scrollHeight;
    }
  }catch(e){
    if(e.name==="AbortError"){aborted=true;text+=(text?"\n\n":"")+"*(stopped)*";}
    else err=e.message;
  }
  bot.classList.remove("streaming");
  if(err){bot.classList.add("err");bot.textContent="⚠ "+err;}
  else bot.innerHTML=md(text)||"<p><i>(empty response)</i></p>";
  state.streaming=false;state.ctrl=null;setInputs(false);
   if(!err&&!aborted){
    try{
      state.meta=await api("/api/sessions/"+state.sid);
      renderAll();
      setView(view);
    }catch(_){}
  }
}

function setInputs(busy){
  const sb=$("#sendBtn");
  sb.disabled=false;sb.textContent=busy?"Stop":"Send";sb.classList.toggle("stop",busy);
  $("#msgInput").disabled=false;
  $("#startNextBtn").disabled=busy;
  $("#prevLessonBtn").disabled=busy;
  document.querySelectorAll("#topicChips .chip").forEach(c=>c.style.pointerEvents=busy?"none":"");
}

const input=$("#msgInput");
$("#sendBtn").onclick=()=>{
  if(state.streaming){ state.ctrl?.abort(); return; }
  sendMsg();
};
input.addEventListener("keydown",e=>{
  if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();if(!state.streaming)sendMsg();}
});
input.addEventListener("input",()=>{
  input.style.height="auto";input.style.height=Math.min(input.scrollHeight,130)+"px";
});
function sendMsg(){
  const v=input.value.trim();
  if(!v)return;
  input.value="";input.style.height="auto";
  streamChat({action:"ask",message:v},state.view);
}

async function openTest(idx,force){
  showOverlay(force?"Writing fresh questions…":"Generating your test…");
  let data;
  try{ data=await api(`/api/sessions/${state.sid}/test/${idx}?force=${force?"true":"false"}`,{method:"POST"}); }
  catch(e){ hideOverlay(); toast(e.message); return; }
  hideOverlay();
  if(data.passed&&!force){ toast("You already passed this test"); renderLessons(); return; }
  buildTestModal(idx,data.questions,false,null);
}

function buildTestModal(idx,questions,graded,result){
  closeModal();
  const back=document.createElement("div");
  back.className="modal-back";back.id="modalRoot";
  let inner="";
  questions.forEach((q,qi)=>{
    const correctIdx=graded?result.results[qi].answer:null;
    inner+=`<div class="qblock ${graded?(result.results[qi].correct?'pass':'fail'):''}" data-q="${qi}">
      <div class="qq">${qi+1}. ${esc(q.question)}</div>
      ${q.options.map((o,oi)=>`<button class="opt${graded&&oi===correctIdx?' correct':(graded&&result.answers[qi]===oi?' wrong':'')}"
        data-q="${qi}" data-o="${oi}" ${graded?"disabled":""}>${String.fromCharCode(65+oi)}. ${esc(o)}</button>`).join("")}
      ${graded?`<div class="expl show">${result.results[qi].correct?"✓ Correct. ":"✗ Wrong. Correct answer: "+esc(q.options[correctIdx])+". "}${esc(result.results[qi].explanation||"")}</div>`:""}
    </div>`;
  });
  const answers=graded?null:new Array(questions.length).fill(null);
  back.innerHTML=`<div class="modal">
    <div class="modal-head"><h3>🧪 Lesson test${graded?` — result`:``}</h3>
      <span id="scoreSpot" class="scoreline"></span>
      <button class="x" id="modalX">✕</button></div>
    <div class="modal-body">${inner}</div>
    <div class="modal-foot">
      <span id="footNote" style="flex:1;font-size:12px;color:var(--dim)">${
        graded?(result.passed?"Passed! Lesson unlocked.":`Score ${(result.score*100)|0}% — you need ${60}% to pass.`)
        :"Pick an answer for every question."}</span>
      ${graded
        ?(result.passed
          ?`<button class="btn green" id="contBtn">Continue to next lesson →</button>`
          :`<button class="btn" id="retryBtn">Retry same test</button><button class="btn primary" id="newqBtn">New questions</button>`)
        :`<button class="btn primary" id="submitBtn">Submit test</button>`}
    </div></div>`;
  document.body.appendChild(back);
  back.onclick=e=>{ if(e.target===back&&!graded) closeModal(); };
  $("#modalX").onclick=closeModal;

  if(!graded){
    back.querySelectorAll(".opt").forEach(b=>b.onclick=()=>{
      const qi=+b.dataset.q;
      back.querySelectorAll(`.opt[data-q="${qi}"]`).forEach(x=>x.classList.remove("sel"));
      b.classList.add("sel");answers[qi]=+b.dataset.o;
    });
    $("#submitBtn").onclick=async()=>{
      if(answers.some(a=>a===null)){toast("Answer all questions first");return;}
      $("#submitBtn").disabled=true;
      try{
        const res=await api(`/api/sessions/${state.sid}/test/${idx}/submit`,{method:"POST",
          headers:{"Content-Type":"application/json"},body:JSON.stringify({answers})});
        state.meta=await api("/api/sessions/"+state.sid);
        renderLessons();updateProgress();
        buildTestModal(idx,questions.map(q=>({...q,answer:q.answer})),true,{...res,answers});
        if(res.passed)toast("Test passed — lesson complete!");
      }catch(e){toast(e.message);$("#submitBtn").disabled=false;}
    };
  }else{
    $("#scoreSpot").innerHTML=result.passed
      ?`<b style="color:var(--accent2)">${Math.round(result.score*100)}%</b>`
      :`<b style="color:var(--danger)">${Math.round(result.score*100)}%</b>`;
    const cont=$("#contBtn");
    if(cont)cont.onclick=()=>{closeModal();streamChat({action:"next_lesson"},"course");};
    const rt=$("#retryBtn");if(rt)rt.onclick=()=>buildTestModal(idx,questions,false,null);
    const nq=$("#newqBtn");if(nq)nq.onclick=()=>openTest(idx,true);
  }
}
function closeModal(){ $("#modalRoot")?.remove(); }
document.addEventListener("keydown",e=>{ if(e.key==="Escape")closeModal(); });

function openFilesModal(){
  const docs=state.meta?.docs||[];
  const rows=docs.length?docs.map(d=>`
    <div class="docrow"><span class="dn">📄 ${esc(d.name)}</span>
      <span class="dm">${d.chunks} chunks · ${(d.bytes/1024).toFixed(0)} KB</span>
      <button class="btn sm danger" data-del="${esc(d.name)}">Remove</button></div>`).join("")
    :`<p style="color:var(--dim);font-size:13px">No documents yet.</p>`;
  closeModal();
  const back=document.createElement("div");
  back.className="modal-back";back.id="modalRoot";
  back.innerHTML=`<div class="modal" style="max-width:560px">
    <div class="modal-head"><h3>📄 Documents in this session</h3><button class="x" id="modalX">✕</button></div>
    <div class="modal-body">${rows}</div>
    <div class="modal-foot"><button class="btn primary" id="addFilesBtn">+ Add files</button></div></div>`;
  document.body.appendChild(back);
  $("#modalX").onclick=closeModal;
  back.onclick=e=>{ if(e.target===back) closeModal(); };
  $("#addFilesBtn").onclick=()=>{$("#fileInput").click()};
  back.querySelectorAll("[data-del]").forEach(b=>b.onclick=async()=>{
    if(!confirm(`Remove "${b.dataset.del}" from this session? Its indexed text is erased.`))return;
    try{
      await api(`/api/sessions/${state.sid}/docs/${encodeURIComponent(b.dataset.del)}`,{method:"DELETE"});
      toast("Document removed");
      state.meta=await api("/api/sessions/"+state.sid);
      renderAll();openFilesModal();
    }catch(e){toast(e.message)}
  });
}

(async ()=>{
  await loadStatus(); setInterval(loadStatus,15000);
  const list=await loadSessions();
  if(list.length){ openSession(list[0].id); }
  else{
    $("#askHero").innerHTML=`<h2>Welcome to OfflineTutor</h2>
      <p>Create a study session, upload your PDFs and notes, then learn with<br>grounded Q&amp;A, full courses, or topic deep-dives — all offline.</p>`;
    $("#askHero").classList.remove("hidden");
  }
})();
