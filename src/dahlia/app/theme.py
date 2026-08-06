"""Visual language derived from the approved Figma concept."""

APP_CSS = r"""
:root {
  --dahlia-primary: #6B5DD3;
  --dahlia-primary-soft: rgba(107, 93, 211, 0.08);
  --dahlia-text: #17171b;
  --dahlia-muted: #777780;
  --dahlia-border: #e3e3e8;
  --dahlia-surface: #ffffff;
  --dahlia-subtle: #f7f7f9;
  --dahlia-danger: #c93f4b;
}

html, body, #app, .nicegui-content {
  width: 100%;
  min-width: 0;
  height: 100%;
  margin: 0;
  overflow: hidden;
  background: var(--dahlia-surface);
  color: var(--dahlia-text);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
               "Segoe UI", sans-serif;
}

body.body--dark { background: var(--dahlia-surface) !important; }
.nicegui-content { padding: 0 !important; }

.dahlia-root {
  width: 100%;
  height: 100vh;
  min-height: 620px;
  overflow: auto;
}

.dahlia-header {
  width: 100%;
  min-height: 53px;
  padding: 0 24px;
  border-bottom: 1px solid var(--dahlia-border);
  background: #fff;
}

.dahlia-brand {
  font-family: "Cascadia Mono", "JetBrains Mono", Consolas, monospace;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .18em;
  text-transform: uppercase;
  color: rgba(23, 23, 27, .62);
}

.dahlia-version, .dahlia-mono, .dahlia-summary, .dahlia-ticks {
  font-family: "Cascadia Mono", "JetBrains Mono", Consolas, monospace;
}

.dahlia-version { font-size: 10px; color: var(--dahlia-muted); }
.dahlia-muted { color: var(--dahlia-muted); }
.dahlia-link { color: var(--dahlia-muted); text-decoration: underline; text-underline-offset: 2px; }
.dahlia-link:hover { color: var(--dahlia-text); }

.dahlia-setup-page {
  width: 100%;
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.dahlia-setup-main {
  flex: 1;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 36px;
}

.dahlia-card {
  width: min(460px, calc(100vw - 72px));
  padding: 30px;
  border: 1px solid var(--dahlia-border);
  border-radius: 9px;
  box-shadow: 0 12px 36px rgba(20, 20, 30, .06);
  background: #fff;
}

.dahlia-title { font-size: 21px; line-height: 1.2; font-weight: 540; margin-bottom: 22px; }
.dahlia-field-label { font-size: 14px; font-weight: 520; margin-bottom: 6px; }
.dahlia-field { width: 100%; }
.dahlia-field .q-field__control { border-radius: 6px; background: #fff; }
.dahlia-field .q-field__native, .dahlia-field .q-field__input { font-size: 14px; }

.dahlia-primary-btn {
  background: var(--dahlia-primary) !important;
  color: white !important;
  border-radius: 6px !important;
  min-height: 43px !important;
  font-size: 14px !important;
  font-weight: 560 !important;
  text-transform: none !important;
  box-shadow: none !important;
}
.dahlia-primary-btn:hover { opacity: .92; }
.dahlia-secondary-btn {
  color: var(--dahlia-text) !important;
  border: 1px solid var(--dahlia-border) !important;
  border-radius: 6px !important;
  min-height: 40px !important;
  text-transform: none !important;
  box-shadow: none !important;
  background: white !important;
}
.dahlia-danger-btn {
  background: var(--dahlia-danger) !important;
  color: white !important;
  border-radius: 6px !important;
  text-transform: none !important;
  box-shadow: none !important;
}

.dahlia-error {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #efb9bf;
  border-radius: 6px;
  background: #fff4f5;
  color: #9f2f39;
  font-size: 13px;
}

.dahlia-settings-bar {
  width: 100%;
  min-height: 34px;
  padding: 6px 24px;
  border-bottom: 1px solid var(--dahlia-border);
  background: rgba(247,247,249,.72);
}
.dahlia-summary { font-size: 11px; color: var(--dahlia-muted); gap: 22px; }
.dahlia-summary b { color: var(--dahlia-text); font-weight: 500; }

.dahlia-experiment-main {
  width: 100%;
  flex: 1;
  min-height: 0;
  padding: 14px 28px 20px;
  display: flex;
  justify-content: center;
  overflow: auto;
}
.dahlia-experiment-content { width: min(1080px, 100%); min-width: 780px; }
.dahlia-chart-frame {
  width: 100%;
  height: clamp(410px, calc(100vh - 315px), 680px);
  min-height: 380px;
}
.dahlia-chart-frame .js-plotly-plot { width: 100% !important; height: 100% !important; }

.dahlia-prediction-label {
  font-family: "Cascadia Mono", "JetBrains Mono", Consolas, monospace;
  color: var(--dahlia-muted);
  font-size: 11px;
}
.dahlia-prediction-label b { color: var(--dahlia-text); font-weight: 600; }

.dahlia-slider .q-slider__track-container { height: 6px; }
.dahlia-slider .q-slider__selection { background: var(--dahlia-primary); }
.dahlia-slider .q-slider__thumb { color: var(--dahlia-primary); }

.dahlia-tick-row {
  width: 100%;
  display: flex;
  justify-content: space-between;
  margin-top: -4px;
  color: var(--dahlia-muted);
  font-size: 9px;
  line-height: 1;
  user-select: none;
}
.dahlia-tick { text-align: center; transform: translateX(0); }
.dahlia-tick::before {
  content: "";
  display: block;
  width: 1px;
  height: 6px;
  background: var(--dahlia-border);
  margin: 0 auto 3px;
}

.dahlia-controls {
  width: 100%;
  margin-top: 16px;
  padding-bottom: 14px;
}
.dahlia-number { width: 130px; }
.dahlia-number .q-field__control { font-family: "Cascadia Mono", Consolas, monospace; }

.dahlia-modal-card {
  width: 390px;
  max-width: calc(100vw - 48px);
  padding: 24px;
  border: 1px solid var(--dahlia-border);
  border-radius: 9px;
  background: white;
}
.dahlia-modal-title { font-size: 16px; font-weight: 560; }
.dahlia-modal-copy { font-size: 14px; line-height: 1.55; color: var(--dahlia-muted); }

.dahlia-results-main {
  width: 100%;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 36px;
  overflow: auto;
}
.dahlia-results { width: min(640px, calc(100vw - 72px)); }
.dahlia-results-table {
  width: 100%;
  border: 1px solid var(--dahlia-border);
  border-radius: 7px;
  overflow: hidden;
}
.dahlia-results-table .q-table__container { box-shadow: none; border-radius: 0; }
.dahlia-results-table thead tr { background: rgba(247,247,249,.8); }
.dahlia-results-table th {
  color: var(--dahlia-muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .06em;
}
.dahlia-results-table td { font-size: 14px; }
.dahlia-results-table td:nth-child(2), .dahlia-results-table td:nth-child(3) {
  font-family: "Cascadia Mono", Consolas, monospace;
}

.dahlia-loading-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255,255,255,.76);
  backdrop-filter: blur(2px);
}
.dahlia-loading-box {
  min-width: 250px;
  padding: 24px 28px;
  border: 1px solid var(--dahlia-border);
  border-radius: 8px;
  background: white;
  box-shadow: 0 14px 40px rgba(20,20,30,.1);
}

@media (max-height: 720px) {
  .dahlia-chart-frame { height: 390px; }
  .dahlia-experiment-main { padding-top: 8px; }
}
"""

ESCAPE_AND_EXIT_GUARD = r"""
<script>
window.__dahliaExperimentActive = false;
document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    event.preventDefault();
    event.stopImmediatePropagation();
  }
}, true);
window.addEventListener('beforeunload', function(event) {
  if (window.__dahliaExperimentActive) {
    event.preventDefault();
    event.returnValue = '';
  }
});
</script>
"""
