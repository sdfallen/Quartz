"""Quartz desktop JavaScript fragment; composed in the shared application scope."""

JAVASCRIPT = r"""  let desktopView={code:'normal',stop_ref:null};
  function renderDesktopTaskState(view) {
    desktopView=view;
    document.getElementById('desktopTaskBar').dataset.state=view.code;
    document.getElementById('desktopTaskLabel').textContent=view.label;
    document.getElementById('desktopTaskDetail').textContent=(view.conversation_id&&view.conversation_id!==currentConvId?'Başka bir sohbetin görevi. ':'')+view.detail;
    const stop=document.getElementById('btnDesktopTaskStop');
    stop.hidden=!view.stop_ref;stop.disabled=!view.stop_ref;
    const isControlActive=(view.code==='active'||view.code==='preparing')&&!!view.stop_ref;
    document.body.classList.toggle('screen-control-active',isControlActive);
    if(typeof renderCrew==='function')renderCrew();
    const hud=document.getElementById('screenControlHud');
    if(hud){
      hud.hidden=!isControlActive;
      const hudSub=document.getElementById('screenControlHudSub');
      if(hudSub)hudSub.textContent=view.label||'Yalnız bu tuşla durdurulur';
    }
    for(const card of document.querySelectorAll('[data-desktop-plan]')) {
      const stillPending=card.dataset.desktopPlan===view.pending_id;
      const start=card.querySelector('[data-desktop-approve]');
      if(start&&!stillPending){start.disabled=true;start.title='Bu kart artık geçerli bir onay isteği değil.';}
      const abandon=card.querySelector('[data-desktop-abandon]');if(abandon)abandon.disabled=!stillPending;
    }
  }
  document.getElementById('btnHudStopTask')?.addEventListener('click',()=>{
    document.getElementById('btnDesktopTaskStop')?.click();
  });
  async function refreshDesktopTaskState() {
    try {
      const r=await window.pywebview.api.desktop_task_status();
      if(r.status!=='ok')throw new Error(r.data);
      renderDesktopTaskState(r.data);
    } catch(e) {
      document.getElementById('desktopTaskLabel').textContent='Masaüstü durumu okunamıyor';
      document.getElementById('desktopTaskDetail').textContent='Erişim var veya bırakıldı varsayılmıyor. '+String(e);
    }
  }
  document.getElementById('btnDesktopTaskStop').onclick=async()=>{
    if(typeof resolveActiveConfirm==='function'&&activeConfirmResolver)resolveActiveConfirm(false);
    const ref=desktopView.stop_ref;if(!ref)return;
    const r=await window.pywebview.api.desktop_task_stop(ref);
    if(r.status!=='ok')appendMsg('err','QUARTZ',r.data);
    await refreshDesktopTaskState();
  };

  let coordinationTimer=null;
  async function pollNaturalTask() {
    const r=await window.pywebview.api.natural_status();
    if(r.status!=='ok')return;
    const state=r.data, pending=state.pending;
    if(typeof setCrewDesktop==='function')setCrewDesktop(state);
    activeTaskSquad = state.active && state.squad && state.job?.conversation_id === currentConvId
      ? {...state.squad, conversation_id:state.job.conversation_id} : null;
    if (activeTaskSquad) updateSquadBadge(activeTaskSquad);
    // A paused card re-renders when expiry or runtime cleanup changes; approval
    // stays disabled until the backend confirms the previous turn has exited.
    const pause=state.job?.pause||null;
    const cleanupReady=!pause||pause.cleanup_confirmed!==false;
    const cardKey=pending?`${pending.id}|${pending.expired?1:0}|${cleanupReady?1:0}`:'';
    for(const card of document.querySelectorAll('[data-natural-permission]')) {
      if(!pending||card.dataset.naturalPermission!==pending.id||card.dataset.cardKey!==cardKey||pending.conversation_id!==currentConvId)card.remove();
    }
    if(!pending||pending.conversation_id!==currentConvId||document.querySelector(`[data-natural-permission="${pending.id}"]`))return;
    pending.approvalBlocked=!cleanupReady||Boolean(pending.expired);
    if(!pending.approvalBlocked && document.getElementById('mainPermissionLevel')?.value==='full' && !['warband','elevation'].includes(pending.kind)) {
      try {
        const autoReply=await window.pywebview.api.natural_approve(pending.id,true);
        if(autoReply.status==='ok'){
          logLine('Tam Yetki aktif: Masaüstü kapsamı otomatik onaylandı.');
          await refreshDesktopTaskState();
          return;
        }
      } catch(_) {}
    }
    const panel=document.createElement('section');panel.className='coordination-card';panel.dataset.naturalPermission=pending.id;panel.dataset.cardKey=cardKey;
    panel.setAttribute('aria-label','Görev için uygulama izni');
    const title=document.createElement('strong');title.textContent=pending.kind==='warband'?'Warband görev izni gerekiyor':'Uygulama izni gerekiyor';
    const reason=document.createElement('p');reason.textContent=pending.reason;
    const summary=document.createElement('p');
    summary.textContent=`${pending.operator==='codex'?'Codex':'Gemini'} yalnız ${pending.targets.map(t=>t.title).join(', ')||'onaylı günlüklerde'} çalışacak. `+
      (pending.logs.length?`Salt okunur günlükler: ${pending.logs.join(', ')}. `:'')+
      'Süre bitince veya Durdur ile erişim bırakılır. Yeni kapsam ayrıca sorulur.';
    if(pending.kind==='warband') {
      const labels={inspect:'Kaynak, RGL ve test kanıtlarını inceleme',develop:'UM yedeği ardından kaynak düzeltme ve resmî derleme',play:'Gerçek oyun kontrolü ve geçici Standard150 ortak ayarı'};
      summary.textContent=(pending.capabilities||[]).map(c=>labels[c]||c).join(' · ')+'. Orijinal kayıtlar yazmaya karşı kilitlenir. İkinci ajan salt okunur inceleme yapar. Durdur girdiyi bırakır; açık oyun kapanana kadar ayar geri yükleme izleyicisi sürer.';
    }
    const details=document.createElement('details');const label=document.createElement('summary');label.textContent='İzin kapsamı ve teknik ayrıntılar';
    const trace=document.createElement('pre');trace.textContent=JSON.stringify({targets:pending.targets,logs:pending.logs,capabilities:pending.capabilities,expires_at:pending.expires_at},null,2);
    details.append(label,trace);
    const approve=document.createElement('button');approve.textContent='Bu görev için izin ver';
    const deny=document.createElement('button');deny.textContent='İzin verme';
    const status=document.createElement('p');
    if(pending.kind==='elevation') {
      title.textContent='Windows yönetici onayı gerekiyor';
      summary.textContent=(pending.launch?.exe || 'Doğrulanmış uygulama yolu bulunamadı')+
        '\nUAC onayını Windows ekranında siz verirsiniz. Quartz yönetici yapılmaz. Bu onay yalnız başlatma içindir; ajana ayar değiştirme talimatı vermez.';
      trace.textContent=JSON.stringify({launch:pending.launch,phase:pending.phase,expires_at:pending.expires_at},null,2);
      approve.textContent='Windows UAC isteğini aç';
      approve.disabled=pending.phase==='prompting'||!pending.launch;
      if(pending.phase==='prompting')status.textContent='Windows yanıtı bekleniyor. Açılmış UAC istemini iptal etmek için Windows ekranında Hayır seçin.';
    }
    const pauseNote=document.createElement('p');pauseNote.className='pause-note';pauseNote.setAttribute('role','status');
    if(state.job?.status==='awaiting_approval')
      pauseNote.textContent='Görev duraklatıldı. Onay verene kadar ajan bilgisayarda işlem yapmaz; Durdur her zaman kullanılabilir.';
    if(!cleanupReady){
      approve.disabled=true;
      status.textContent='Önceki ajan turu kapatılıyor; onay, temizlik doğrulanınca açılacak.';
    }
    let refresh=null;
    if(pending.expired){
      title.textContent='İzin süresi doldu';
      approve.disabled=true;approve.hidden=true;
      status.textContent='Devam için yeni onay gerekli. Bu kart artık izin vermez.';
      refresh=document.createElement('button');refresh.textContent='Yeniden onay hazırla';
      // Reissue is NOT approval: it returns a new request the user approves separately.
      refresh.onclick=async()=>{
        refresh.disabled=true;
        try {
          const reply=await window.pywebview.api.natural_refresh_permission(pending.id,currentConvId,true);
          if(!reply||reply.status!=='ok')throw new Error(reply?.data||'Yeni onay hazırlanamadı');
          panel.remove();
          await pollNaturalTask();
        } catch(error) {
          status.textContent='Yeni onay hazırlanamadı: '+String(error.message||error);
          refresh.disabled=false;
        }
      };
    }
    const decide=async(accept)=>{
      approve.disabled=true;deny.disabled=true;
      let resolved=false;
      try {
        const reply=await window.pywebview.api[accept?'natural_approve':'natural_deny'](pending.id,...(accept?[true]:[]));
        if(!reply || reply.status!=='ok') throw new Error(reply?.data || 'İzin yanıtı alınamadı');
        resolved=true;panel.remove();
        await refreshDesktopTaskState();
        await pollNaturalTask();
      } catch(error) {
        status.textContent='İzin işlemi doğrulanamadı: '+String(error.message||error)+'. Güncel görev durumu yeniden okunmalı.';
      } finally {
        if(!resolved){approve.disabled=pending.approvalBlocked===true;deny.disabled=false;}
      }
    };
    approve.onclick=()=>decide(true);deny.onclick=()=>decide(false);
    panel.append(title,...(pauseNote.textContent?[pauseNote]:[]),reason,summary,details,approve,deny,...(refresh?[refresh]:[]),status);
    chatEl.append(panel);scrollToBottom(true);
  }
  async function pollCoordination() {
    await refreshDesktopTaskState();
    const response=await window.pywebview.api.coordination_status();
    if(response.status!=='ok')return;
    if(response.data.job){
      const job=response.data.job;
      const state=document.querySelector(`[data-coordination-status="${job.id}"]`);
      if(state)state.textContent=({running:'Çalışıyor; ajan mesajları aşağıda.',starting:'Başlatılıyor.',completed:'Çalışma sona erdi; hedefin sonucunu ajan kanıtlarından kontrol edin.',failed:'Başarısız; ayrıntılar ajan mesajlarında.',cancelled:'Durduruldu.',expired:'Onaylanan süre doldu; kontrol bırakıldı.'})[job.status]||job.status;
      const stop=document.querySelector(`[data-coordination-stop="${job.id}"]`);if(stop)stop.disabled=!response.data.active;
    }
    const messages=await window.pywebview.api.chat_status();
    if(messages.status==='ok'&&messages.data.active_conversation?.id===currentConvId)
      syncConversationMessages(messages.data.active_conversation.messages,false);
    if(response.data.active)coordinationTimer=setTimeout(pollCoordination,1500);
    else if(coordinationTimer){clearTimeout(coordinationTimer);coordinationTimer=null;}
  }

"""
