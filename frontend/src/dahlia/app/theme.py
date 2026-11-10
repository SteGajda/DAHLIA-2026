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

/* ── Sidebar layout (all screens except Active Experiment) ── */

.dahlia-page-row {
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  height: 100vh;
  width: 100%;
  overflow: hidden;
  align-items: stretch;
}

.dahlia-sidebar {
  display: flex !important;
  flex-direction: column !important;
  width: 180px;
  min-width: 180px;
  max-width: 180px;
  flex-shrink: 0;
  height: 100%;
  border-right: 1px solid var(--dahlia-border);
  background: var(--dahlia-subtle);
  overflow: hidden;
}

.dahlia-sidebar-top {
  padding: 16px 14px 12px;
  border-bottom: 1px solid var(--dahlia-border);
}

.dahlia-sidebar-nav { flex: 1; padding: 8px 0; }
.dahlia-sidebar-bottom { padding: 6px 0; border-top: 1px solid var(--dahlia-border); }

.dahlia-nav-item {
  width: 100% !important;
  padding: 9px 14px !important;
  font-size: 14px !important;
  color: var(--dahlia-text) !important;
  background: transparent !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  text-transform: none !important;
  justify-content: flex-start !important;
  min-height: unset !important;
  transition: background 0.12s;
}
/* Quasar q-btn__content defaults to justify-center — override to left */
.dahlia-nav-item .q-btn__content {
  justify-content: flex-start !important;
  width: 100% !important;
}
.dahlia-nav-item:hover { background: rgba(107, 93, 211, 0.07) !important; }
.dahlia-nav-item.active {
  background: var(--dahlia-primary-soft) !important;
  color: var(--dahlia-primary) !important;
  font-weight: 520 !important;
}

/* ── Connection / sync badges ─────────────────────────────────── */
.dahlia-status-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 20px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .04em;
  white-space: nowrap;
}
.dahlia-status-online  { background: #d4f7e8; color: #1a7a4a; }
.dahlia-status-offline { background: #f0f0f4; color: #6b6b75; }
.dahlia-sync-local   { background: #f0f0f4; color: #555560; }
.dahlia-sync-pending { background: #fff0dc; color: #8a5700; }
.dahlia-sync-synced  { background: #d4f7e8; color: #1a7a4a; }
.dahlia-sync-failed  { background: #ffe4e6; color: #9f2f39; }

/* ── Content column right of sidebar ──────────────────────────── */
.dahlia-content-page {
  display: flex !important;
  flex-direction: column !important;
  flex: 1 1 0 !important;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.dahlia-content-header {
  width: 100%;
  min-height: 53px;
  padding: 0 28px;
  border-bottom: 1px solid var(--dahlia-border);
  background: #fff;
  flex-shrink: 0;
  align-items: center;
}

.dahlia-content-main { flex: 1; overflow: auto; padding: 36px; }

/* setup-main and results-main fill remaining height and scroll if needed */
.dahlia-setup-main   { flex: 1 !important; min-height: 0; overflow: auto; }
.dahlia-results-main { flex: 1 !important; min-height: 0; overflow: auto; }

/* ── Profile / auth ───────────────────────────────────────────── */
.dahlia-profile-card {
  width: min(460px, calc(100vw - 220px));
  padding: 30px;
  border: 1px solid var(--dahlia-border);
  border-radius: 9px;
  box-shadow: 0 12px 36px rgba(20, 20, 30, .06);
  background: #fff;
}

.dahlia-back-link {
  font-size: 13px !important;
  color: var(--dahlia-muted) !important;
  text-transform: none !important;
  box-shadow: none !important;
  background: transparent !important;
  padding: 0 !important;
  min-height: unset !important;
  letter-spacing: 0 !important;
}
.dahlia-back-link:hover { color: var(--dahlia-text) !important; }

.dahlia-checkbox .q-checkbox__label { font-size: 14px; }
.dahlia-checkbox-consent .q-checkbox__label { font-size: 13px; color: var(--dahlia-muted); }

.dahlia-profile-info-label {
  font-size: 12px;
  color: var(--dahlia-muted);
  font-weight: 500;
  min-width: 140px;
}

/* ── My Results ───────────────────────────────────────────────── */
.dahlia-my-results-table {
  width: 100%;
  border: 1px solid var(--dahlia-border);
  border-radius: 7px;
  overflow: hidden;
  background: #fff;
}

.dahlia-export-btn {
  border: 1px solid var(--dahlia-border) !important;
  border-radius: 5px !important;
  font-size: 11px !important;
  font-weight: 700 !important;
  letter-spacing: .06em !important;
  text-transform: uppercase !important;
  box-shadow: none !important;
  min-height: 30px !important;
  padding: 0 10px !important;
  color: var(--dahlia-muted) !important;
  background: white !important;
}
.dahlia-export-btn.active {
  background: var(--dahlia-primary) !important;
  color: white !important;
  border-color: var(--dahlia-primary) !important;
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
