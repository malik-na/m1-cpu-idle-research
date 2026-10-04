// Throwaway C. All interactions inspect fixed evidence or prospective gates; no hardware action.
(() => {
  const claims = {
    native: {title:'Native Linux', status:'Runtime evidence', description:'Published packets target base-M1 T8103/J313, with boot and source identities recorded for each capture.', support:'Native observation is distinct from guest tracing or source-permitted behavior. Each packet has its own instrument and conditions.', next:'Follow the packet identities, raw records and replay path before extending a claim.', source:'/read/wiki/Findings-Index.html'},
    command: {title:'Command ordering', status:'Observed before DSB', description:'ABI 3 retained 2,185 first-attempt pre-DSB command reads. BUSY was set in 71; 18 satisfy the strict software final-entrant ticket screen.', support:'A bounded command-state observation before DSB, linked to software observer order. No BUSY observation at the later executed WFI instruction.', next:'A genuinely independent timing signal is required before further #5 reboots. The issue stays open with this limit.', source:'/read/experiments/aurora-apsc-observer/ABI3-E-TICKET-RESULT.html'},
    software: {title:'Software state', status:'Ordered observer tickets', description:'In a post-hoc screen, six ABI 3 witnesses have every peer observer idle-exit ticket following the candidate’s post-WFI idle-exit ticket.', support:'Order between software observation points. It does not locate a peer inside its exit path or prove that a peer was physically asleep.', next:'An independently calibrated physical-state signal must be associated with the software intervals.', source:'/read/experiments/aurora-apsc-observer/ABI3-E-TICKET-RESULT.html'},
    physical: {title:'Physical state', status:'Contrast unresolved', description:'Sparse PCPM sampling returned the same full word in all 90 reads, including 24 guarded all-P-released samples. The declared ACTUAL contrast failed.', support:'A negative signal screen for this register and these conditions. Constant ACTUAL = 15 does not rule out deeper states or establish rail power.', next:'First qualify records-only acquisition on the unbooted PS3 image. PCPU-slot access and then state meaning require separate gates.', source:'/read/experiments/linux-pcpm-sampler/native-evidence/mmio-abi2/README.html'},
    energy: {title:'Energy consequence', status:'Not measured', description:'The published command and PMGR packets do not measure energy savings, CPU-rail power or an idle-policy benefit.', support:'No energy inference follows from BUSY, software tickets, register names or a constant state code alone.', next:'A separately qualified energy and wake measurement, with matched workloads and observer controls, would assess consequences.', source:'/read/experiments/linux-pcpm-sampler/PCPU-PS3-PROTOCOL.html'}
  };
  const fieldText = {
    actual:'ACTUAL is bits 7:4. Here 1111₂ = 15. This is the decoded numeric field; CPU-slot physical meaning is not calibrated.',
    desired:'DESIRED is bits 3:0. Here 0000₂ = 0. A requested code is not proof of a completed CPU transition.',
    remaining:'Bits 31:8 are retained in the raw word. Their latch and clear behavior is uncalibrated here; this prototype assigns no physical meaning to them.'
  };
  let node = 'physical', field = 'actual', mode = 'recorded', initialized = false;
  function render() {
    const root = document.getElementById('VariantC');
    const claim = claims[node];
    root.querySelectorAll('[data-map-node]').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.mapNode === node)));
    root.querySelector('#map-node-status').textContent = claim.status;
    root.querySelector('#map-node-title').textContent = claim.title;
    root.querySelector('#map-node-description').textContent = claim.description;
    root.querySelector('#map-node-support').textContent = claim.support;
    root.querySelector('#map-node-next').textContent = claim.next;
    root.querySelector('#map-node-source').href = claim.source;
    root.querySelectorAll('[data-map-mode]').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.mapMode === mode)));
    root.querySelector('.map-recorded').hidden = mode !== 'recorded';
    root.querySelector('.map-planned').hidden = mode !== 'planned';
    root.querySelectorAll('[data-map-field]').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.mapField === field)));
    root.querySelectorAll('.map-bit').forEach(b => b.classList.toggle('is-selected',b.dataset.field === field));
    root.querySelector('#map-field-explanation').textContent = fieldText[field];
    if (window.prototypeState) window.prototypeState({node, word: mode === 'recorded' ? '0x000021f0' : 'PCPU values unknown; no PS3 boot', meaning:claim.support, field: mode === 'recorded' ? field : 'not acquired', mode, nextGate:'PS3 fresh boot: records 2 800 0; zero MMIO; review before second boot', sourceCap:'two rows; at most ten 32-bit attempts on conditional MMIO boot', image:'installed and read back; unbooted'});
  }
  window.initVariantC = () => {
    const root = document.getElementById('VariantC');
    if (!initialized) {
      const word = 0x000021f0;
      for(let bit=31;bit>=0;bit--) {
        const item=document.createElement('span');
        item.className='map-bit';
        item.dataset.field=bit>=8?'remaining':bit>=4?'actual':'desired';
        const label=document.createElement('small');label.textContent=bit;
        item.append(String((word>>>bit)&1),label);root.querySelector('#map-bits').append(item);
      }
      for(let i=0;i<90;i++) { const item=document.createElement('i');item.title=`Read ${i+1}: 0x000021f0`;root.querySelector('#map-dot-grid').append(item); }
      root.querySelectorAll('[data-map-node]').forEach(b=>b.addEventListener('click',()=>{node=b.dataset.mapNode;render();}));
      root.querySelectorAll('[data-map-field]').forEach(b=>b.addEventListener('click',()=>{field=b.dataset.mapField;render();}));
      root.querySelectorAll('[data-map-mode]').forEach(b=>b.addEventListener('click',()=>{mode=b.dataset.mapMode;render();}));
      initialized=true;
    }
    render();
  };
})();
