/**
 * Circle Timer Card for Smith Water Heater
 * 圆形时钟预约加热选择器
 */
class CircleTimerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._segments = [false, false, false, false, false, false];
    this._entityId = null;
    this._lastSentOption = null;
  }

  setConfig(config) {
    this._entityId = config.entity;
    this._name = config.name || '预约加热';
    this.render();
  }

  set hass(hass) {
    const oldHass = this._hass;
    this._hass = hass;
    // Only sync from entity on first load or entity change
    if (!oldHass && hass) {
      this._syncFromEntity();
    }
    this.render();
  }

  get hass() {
    return this._hass;
  }

  _syncFromEntity() {
    if (!this._hass || !this._entityId) return;
    const state = this._hass.states[this._entityId];
    if (!state) return;
    const option = state.state;
    if (option === 'unknown' || option === 'unavailable') return;
    // Parse from the option name like "4,8,12,16"
    const parts = option.split(',').map(s => parseInt(s.trim()));
    if (parts.length > 0 && !isNaN(parts[0])) {
      this._segments = [false, false, false, false, false, false];
      for (const h of parts) {
        const idx = h / 4;
        if (idx >= 0 && idx < 6) this._segments[idx] = true;
      }
    } else if (option === '关闭') {
      this._segments = [false, false, false, false, false, false];
    }
  }

  _getOptionName() {
    const hours = [0, 4, 8, 12, 16, 20];
    const active = [];
    for (let i = 0; i < 6; i++) {
      if (this._segments[i]) active.push(hours[i]);
    }
    return active.length === 0 ? '关闭' : active.join(',');
  }

  _sendCommand() {
    if (!this._hass || !this._entityId) return;
    const option = this._getOptionName();
    this._lastSentOption = option;
    this._hass.callService('select', 'select_option', {
      entity_id: this._entityId,
      option: option,
    });
  }

  _segmentPath(cx, cy, r, segmentIndex) {
    const startAngle = segmentIndex * 60;
    const endAngle = (segmentIndex + 1) * 60;
    const innerR = r * 0.42;
    const outerR = r * 0.90;

    const toRad = (deg) => (deg - 90) * Math.PI / 180;
    const ox1 = cx + outerR * Math.cos(toRad(startAngle));
    const oy1 = cy + outerR * Math.sin(toRad(startAngle));
    const ox2 = cx + outerR * Math.cos(toRad(endAngle));
    const oy2 = cy + outerR * Math.sin(toRad(endAngle));
    const ix1 = cx + innerR * Math.cos(toRad(endAngle));
    const iy1 = cy + innerR * Math.sin(toRad(endAngle));
    const ix2 = cx + innerR * Math.cos(toRad(startAngle));
    const iy2 = cy + innerR * Math.sin(toRad(startAngle));

    return `M ${ox1} ${oy1} A ${outerR} ${outerR} 0 0 1 ${ox2} ${oy2} L ${ix1} ${iy1} A ${innerR} ${innerR} 0 0 0 ${ix2} ${iy2} Z`;
  }

  render() {
    const size = 280;
    const cx = size / 2;
    const cy = size / 2;
    const r = size / 2 - 20;

    const labels = ['0', '4', '8', '12', '16', '20'];
    const segmentLabels = ['0-4点', '4-8点', '8-12点', '12-16点', '16-20点', '20-24点'];
    const activeColors = ['#1b5e20', '#2e7d32', '#388e3c', '#43a047', '#4caf50', '#66bb6a'];
    const inactiveColors = ['#e8f5e9', '#c8e6c9', '#a5d6a7', '#81c784', '#66bb6a', '#4caf50'];

    let svg = `<svg viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg">`;

    // Outer ring
    svg += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#e0e0e0" stroke-width="1" opacity="0.5"/>`;

    // Segments
    for (let i = 0; i < 6; i++) {
      const path = this._segmentPath(cx, cy, r, i);
      const fill = this._segments[i] ? activeColors[i] : inactiveColors[i];
      const opacity = this._segments[i] ? 1 : 0.6;
      svg += `<path d="${path}" fill="${fill}" opacity="${opacity}"
               stroke="white" stroke-width="2" style="cursor:pointer"
               data-segment="${i}" class="segment"/>`;
    }

    // Hour marks on outer edge
    for (let i = 0; i < 6; i++) {
      const angle = (i * 60 - 90) * Math.PI / 180;
      const lx = cx + (r + 14) * Math.cos(angle);
      const ly = cy + (r + 14) * Math.sin(angle);
      svg += `<text x="${lx}" y="${ly}" text-anchor="middle" dominant-baseline="central"
               font-size="14" font-weight="bold" fill="#555">${labels[i]}</text>`;
    }

    // Segment labels inside arcs
    for (let i = 0; i < 6; i++) {
      const midAngle = (i * 60 + 30 - 90) * Math.PI / 180;
      const labelR = r * 0.68;
      const lx = cx + labelR * Math.cos(midAngle);
      const ly = cy + labelR * Math.sin(midAngle);
      const label = segmentLabels[i];
      svg += `<text x="${lx}" y="${ly}" text-anchor="middle" dominant-baseline="central"
               font-size="10" fill="${this._segments[i] ? 'white' : '#888'}"
               style="pointer-events:none">${label}</text>`;
    }

    // Center
    const activeCount = this._segments.filter(Boolean).length;
    const centerText = activeCount === 0 ? '已关闭' : `已选${activeCount}段`;
    svg += `<text x="${cx}" y="${cy - 4}" text-anchor="middle" dominant-baseline="central"
             font-size="18" font-weight="bold" fill="#333">${centerText}</text>`;
    svg += `<text x="${cx}" y="${cy + 16}" text-anchor="middle" dominant-baseline="central"
             font-size="11" fill="#999">预约加热</text>`;

    svg += '</svg>';

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .card { padding: 16px; text-align: center; }
        .title { font-size: 16px; font-weight: 500; margin-bottom: 8px; color: var(--primary-text-color); }
        svg { max-width: 280px; margin: 0 auto; display: block; }
        .segment:hover { filter: brightness(1.15); }
        .buttons { margin-top: 12px; display: flex; justify-content: center; gap: 8px; }
        button {
          padding: 6px 20px; border: none; border-radius: 16px; cursor: pointer;
          font-size: 13px; color: white; transition: opacity 0.2s;
        }
        button:hover { opacity: 0.85; }
        .btn-clear { background: #9e9e9e; }
        .btn-all { background: #4caf50; }
      </style>
      <ha-card>
        <div class="card">
          <div class="title">${this._name}</div>
          ${svg}
          <div class="buttons">
            <button class="btn-clear" id="clearBtn">清除全部</button>
            <button class="btn-all" id="allBtn">全选</button>
          </div>
        </div>
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll('.segment').forEach(el => {
      el.addEventListener('click', () => {
        const idx = parseInt(el.dataset.segment);
        this._segments[idx] = !this._segments[idx];
        this._sendCommand();
        this.render();
      });
    });

    this.shadowRoot.getElementById('clearBtn').addEventListener('click', () => {
      this._segments = [false, false, false, false, false, false];
      this._sendCommand();
      this.render();
    });

    this.shadowRoot.getElementById('allBtn').addEventListener('click', () => {
      this._segments = [true, true, true, true, true, true];
      this._sendCommand();
      this.render();
    });
  }

  getCardSize() { return 4; }
}

customElements.define('circle-timer-card', CircleTimerCard);
