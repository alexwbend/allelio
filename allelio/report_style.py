"""Shared, offline branding for both standalone HTML report formats."""

REPORT_CSS = """
:root {
    --report-page: #f9f8fb;
    --report-panel: #eae7ef;
    --report-border: #d9d5df;
    --report-ink: #29272e;
    --report-muted: #625d6b;
    --report-mint: #d8f3e9;
    --report-cyan: #d6f0f7;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                 'Helvetica Neue', Arial, sans-serif;
    color: var(--report-ink);
    background: var(--report-page);
    line-height: 1.6;
}
h1, h2, h3 { color: var(--report-ink); font-weight: 600; }
a { color: #176579; text-underline-offset: 3px; }
a:focus-visible, summary:focus-visible {
    outline: 3px solid #176579; outline-offset: 3px;
}
header {
    background: var(--report-panel); color: var(--report-ink);
    border: 1px solid var(--report-border); border-top: 4px solid #66c8aa;
    border-radius: 12px; box-shadow: none;
}
.stat-card, .summary-section, .variant-card, .summary, .gene-group {
    background: var(--report-page); border: 1px solid var(--report-border);
    border-radius: 12px; box-shadow: 0 1px 2px #29272e0d;
}
.stat-value { color: var(--report-ink); font-size: 38px; font-weight: 500; }
.stat-label { color: var(--report-muted); text-transform: none; letter-spacing: 0; }
.gene-group { padding: 16px 20px; margin: 10px 0; }
.gene-group summary { cursor: pointer; font-weight: 600; }
.gene-group[open] summary {
    border-bottom: 1px solid var(--report-border); padding-bottom: 12px; margin-bottom: 12px;
}
.gene-group ul { padding-left: 24px; }
.gene-group p { margin: 8px 0; }
.tab-nav { background: var(--report-page); border-color: var(--report-border); }
.tab-link, .tab-count { background: var(--report-panel); color: var(--report-ink); }
.link-btn { color: #176579; border-color: var(--report-border); }
.link-btn:hover { background: var(--report-cyan); color: #174e5e; border-color: #176579; }
.ai-note { background: var(--report-cyan); border-color: #27869c; color: #174e5e; }
.gap-note { background: var(--report-panel); color: var(--report-ink); }
footer { background: var(--report-panel); color: var(--report-muted); border: 1px solid var(--report-border); }
.footer-section strong { color: var(--report-ink); }
.footer-meta { color: var(--report-muted); border-color: var(--report-border); }
.variant-card:hover { transform: none; box-shadow: 0 2px 6px #29272e14; }
@media (max-width: 600px) {
    .container { padding: 12px; }
    .variants-grid { grid-template-columns: minmax(0, 1fr); }
    .summary-section { padding: 18px; }
    .gene-group { padding: 12px; }
}
@media print {
    body, header, .stat-card, .summary-section, .variant-card, .gene-group, footer {
        background: white; color: #222; box-shadow: none;
    }
    .gene-group { break-inside: avoid; }
}
"""
