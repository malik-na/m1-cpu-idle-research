/* Throwaway Variant B. All displayed rows come from the published E validator report. */
window.initVariantB = function () {
  const root = document.getElementById('VariantB');
  const witnesses = window.PROTOTYPE_DATA.witnesses;
  const find = id => root.querySelector('#' + id);
  const selector = find('lab-witness');
  const posthoc = witness => witness.peers.every(peer => peer.exit_ticket > witness.candidate_exit_ticket);
  witnesses.forEach((witness, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent = 'CPU ' + witness.cpu + ' / token ' + witness.token + (posthoc(witness) ? ' · +screen' : '');
    selector.append(option);
  });

  function plot(witness) {
    const tickets = [...new Set([witness.candidate_enter_ticket, witness.ticket_pre, witness.ticket_post,
      witness.candidate_exit_ticket, ...witness.peers.flatMap(peer => [peer.enter_ticket, peer.exit_ticket])])].sort((a, b) => a - b);
    const x = ticket => 155 + tickets.indexOf(ticket) * (655 / (tickets.length - 1));
    const rows = [{cpu:witness.cpu, token:witness.token, enter_ticket:witness.candidate_enter_ticket,
      exit_ticket:witness.candidate_exit_ticket, candidate:true}, ...witness.peers];
    const bracketLeft = x(witness.ticket_pre), bracketRight = x(witness.ticket_post);
    const svg = '<svg viewBox="0 0 870 310" role="img" aria-labelledby="lab-chart-title lab-chart-desc">' +
      '<title id="lab-chart-title">Software callback ticket order for CPU ' + witness.cpu + ', token ' + witness.token + '</title>' +
      '<desc id="lab-chart-desc">Recorded command read between tickets ' + witness.ticket_pre + ' and ' + witness.ticket_post +
      '. All three peer callback intervals contain this bracket. Horizontal spacing is ordinal, not elapsed time. Executed WFI is not plotted.</desc>' +
      '<rect x="' + (bracketLeft - 5) + '" y="26" width="' + (bracketRight - bracketLeft + 10) + '" height="237" fill="#c8b2eb" opacity=".12"/>' +
      '<text x="' + ((bracketLeft + bracketRight) / 2) + '" y="15" fill="#c8b2eb" text-anchor="middle" font-size="11">READ</text>' +
      tickets.map(ticket => '<line x1="' + x(ticket) + '" y1="26" x2="' + x(ticket) + '" y2="264" stroke="#333c47" stroke-dasharray="2 5"/>' +
        '<text x="' + x(ticket) + '" y="284" fill="#a1adbb" text-anchor="middle" font-size="11">' + ticket + '</text>').join('') +
      rows.map((row, index) => {
        const y = 55 + index * 61;
        const color = row.candidate ? '#f0bd78' : '#83c9ca';
        return '<text x="8" y="' + (y - 2) + '" fill="' + color + '" font-size="13">CPU ' + row.cpu + '</text>' +
          '<text x="8" y="' + (y + 15) + '" fill="#a1adbb" font-size="10">token ' + row.token + '</text>' +
          '<line x1="' + x(row.enter_ticket) + '" x2="' + x(row.exit_ticket) + '" y1="' + y + '" y2="' + y + '" stroke="' + color + '" stroke-width="10" stroke-linecap="round"/>' +
          '<circle cx="' + x(row.enter_ticket) + '" cy="' + y + '" r="6" fill="#111419" stroke="' + color + '" stroke-width="2"/>' +
          '<circle cx="' + x(row.exit_ticket) + '" cy="' + y + '" r="6" fill="' + color + '"/>' +
          '<text x="' + x(row.enter_ticket) + '" y="' + (y - 15) + '" text-anchor="middle" fill="#a1adbb" font-size="10">enter ' + row.enter_ticket + '</text>' +
          '<text x="' + x(row.exit_ticket) + '" y="' + (y + 23) + '" text-anchor="middle" fill="#a1adbb" font-size="10">exit ' + row.exit_ticket + '</text>';
      }).join('') + '</svg>';
    find('lab-ticket-plot').innerHTML = svg;
  }

  function render() {
    const witness = witnesses[Number(selector.value)];
    const word = BigInt(witness.raw_cmd);
    const busy = Number((word >> 31n) & 1n);
    const low32 = word & 0xffffffffn;
    const bits = low32.toString(2).padStart(32, '0');
    find('lab-candidate-name').textContent = 'CPU ' + witness.cpu + ' / ' + witness.token;
    find('lab-candidate-meta').textContent = 'Cluster ' + witness.cluster + ' · complete witness';
    find('lab-raw-command').textContent = witness.raw_cmd;
    find('lab-busy-value').textContent = String(busy);
    find('lab-low32').textContent = '0x' + low32.toString(16).padStart(8, '0');
    find('lab-command-bits').innerHTML = [0, 8, 16, 24].map(start => '<div class="lab-bit-byte">' +
      [...bits.slice(start, start + 8)].map((bit, offset) => '<span class="lab-bit' + (start + offset === 0 ? ' busy' : '') +
        '" title="Bit ' + (31 - start - offset) + (start + offset === 0 ? ' · BUSY' : '') + '">' + bit + '</span>').join('') + '</div>').join('');
    find('lab-posthoc-status').textContent = posthoc(witness) ? 'Selected row: passes the additional post-hoc callback-order screen.' :
      'Selected row: qualifies for the predeclared read witness; does not pass the post-hoc screen.';
    find('lab-selected-json').textContent = JSON.stringify(witness, null, 2);
    plot(witness);
    if (window.prototypeState) window.prototypeState({
      witness:{cpu:witness.cpu, token:witness.token, cluster:witness.cluster, rawCommand:witness.raw_cmd, busyBit31:busy},
      ticketBracket:[witness.ticket_pre, witness.ticket_post],
      candidateInterval:[witness.candidate_enter_ticket, witness.candidate_exit_ticket],
      peers:witness.peers,
      posthocCallbackScreen:posthoc(witness),
      claim:'Pending command at the recorded pre-DSB read, inside ticket-ordered software callback intervals. BUSY at executed WFI and physical power state are unmeasured.'
    });
  }
  selector.value = String(Math.max(0, witnesses.findIndex(witness => witness.cpu === 4 && witness.token === 177)));
  selector.addEventListener('change', render);
  render();
};
