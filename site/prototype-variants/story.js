/* THROWAWAY UI PROTOTYPE: schematic source order; never live telemetry. */
window.initVariantA = function () {
  const root = document.getElementById('VariantA');
  if (!root || root.dataset.initialized) return;
  root.dataset.initialized = 'true';
  const stages = [
    {stage:'dvfs-set', kind:'Recorded local order', title:'A SET precedes this read.', description:'A successful same-CPU SET targeted cluster 1 before the read. That establishes local event order; other CPUs could also submit cluster commands, so the record does not identify which SET caused BUSY.', detail:'Writer CPU 4 · cluster 1 · local upper lag: 54 counter ticks'},
    {stage:'busy-read', kind:'Native hardware observation', title:'BUSY is set at this read.', description:'CPU 4 / token 177 reads the preserved APSC command word between tickets 1904 and 1905. All three peer CPUs have entered their recorded idle callbacks and have not yet recorded an exit.', detail:'Tickets 1904 → 1905 · raw word 0x0000040080104104 · BUSY bit 31 = 1'},
    {stage:'dsb', kind:'Linked instruction order', title:'The full-system barrier follows.', description:'The existing DSB instruction is after the instrumented read and its ticket bracket. The binary preserves this barrier. There is no command-state sample at the barrier, and no measured continuity from the earlier read.', detail:'Source order: instrumented read → dsb sy → wfi · elapsed gap unmeasured'},
    {stage:'wfi', kind:'Command state unmeasured', title:'BUSY at WFI remains unknown.', description:'The candidate executes WFI after the read bracket. The tickets do not tell us whether BUSY is still set, whether a peer has already left WFI, or whether any core or cluster has entered a physical low-power state.', detail:'No instruction-correlated APSC sample · no calibrated physical-state or energy signal'},
    {stage:'callback-exit', kind:'Recorded software order', title:'A callback exit completes the bracket.', description:'CPU 4 records its callback exit at ticket 1919, after executing WFI. CPU 6’s callback exit is ticket 1906: after the BUSY read bracket, before the candidate exit, and possibly before the candidate’s WFI.', detail:'Peer CPU 6 exit: 1906 · candidate CPU 4 exit: 1919 · tickets establish order, not duration'}
  ];
  const buttons = [...root.querySelectorAll('[data-story-stage]')];
  const nodes = [...root.querySelectorAll('[data-story-node]')];
  function select(index) {
    const item = stages[index];
    buttons.forEach((button, i) => button.setAttribute('aria-pressed', String(i === index)));
    nodes.forEach((node, i) => node.dataset.current = String(i === index));
    root.querySelector('#story-stage-kind').textContent = item.kind;
    root.querySelector('#story-stage-title').textContent = item.title;
    root.querySelector('#story-stage-description').textContent = item.description;
    root.querySelector('#story-stage-detail').textContent = item.detail;
    if (window.prototypeState) window.prototypeState({variant:'A', view:'Editorial story', stage:item.stage, sourceOrderOnly:true, measuredTimeAxis:false, commandStateAtWfi:'unmeasured', physicalState:'unmeasured', candidate:'CPU 4 / token 177', readTickets:[1904,1905], peerExitTicket:1906, candidateExitTicket:1919});
  }
  buttons.forEach((button, index) => button.addEventListener('click', () => select(index)));
  select(0);
};
