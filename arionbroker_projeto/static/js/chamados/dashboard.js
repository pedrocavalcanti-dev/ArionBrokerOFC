/**
 * ARION BROKER — DASHBOARD NOC/TV (SINGLE SCREEN)
 * JS COMPLETO - Lógica de busca de dados, montagem dinâmica do HTML,
 * processamento das arrays e renderização do Chart.js.
 * v4.0 — Cores do gráfico lidas das variáveis de tema (base.css),
 * para acompanhar automaticamente o modo claro/escuro.
 */

// ── UTILS ──────────────────────────────────────────────────
function escapeHtml(str) {
    if (str === null || str === undefined) return '—';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function getCssVar(name, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
}

// ── ESTADO DA UI E CONFIGURAÇÕES ───────────────────────────
let _dadosResumo = null;
let _chartInstance = null;

const STATUS_BASE = ['aberto', 'resolvido', 'atendimento', 'pendente', 'ag_visita', 'analise', 'troca', 'cancelamento', 'aguardando'];
const STATUS_COM_TUNEL = [...STATUS_BASE, 'tunel'];
const STATUS_COM_CGNAT_TUNEL = [...STATUS_BASE, 'cgnat', 'tunel'];

const ESTRUTURA = [
    {
        id: 'claro', nome: 'Claro', cor: 'claro',
        projetos: [
            { id: 'brad_claro', nome: 'Bradesco', col_id: 'BRAD', status_pool: STATUS_COM_CGNAT_TUNEL, analista: 'Pedro Cavalcanti', api_nome: 'Bradesco' },
            { id: 'bb_claro', nome: 'Banco do Brasil', col_id: 'CI', status_pool: STATUS_COM_TUNEL, analista: 'Pedro Cavalcanti', api_nome: 'Banco do Brasil' },
            { id: 'cef_claro', nome: 'Caixa Econômica', col_id: 'CI', status_pool: STATUS_COM_TUNEL, analista: 'Pedro Cavalcanti', api_nome: 'Caixa Econômica' },
            { id: 'correios', nome: 'Correios', col_id: 'CI', status_pool: STATUS_COM_TUNEL, analista: 'Pedro Cavalcanti', api_nome: 'Correios' },
            { id: 'carrefour', nome: 'Carrefour', col_id: 'CI', status_pool: STATUS_COM_TUNEL, analista: 'Pedro Cavalcanti', api_nome: 'Carrefour' },
            { id: 'div_claro', nome: 'Diversos', col_id: 'CI', status_pool: STATUS_BASE, analista: 'Pedro Cavalcanti', api_nome: 'Diversos' },
        ]
    },
    {
        id: 'vivo', nome: 'Vivo', cor: 'vivo',
        projetos: [
            { id: 'brad_vivo', nome: 'Bradesco', col_id: 'BRAD', status_pool: STATUS_COM_CGNAT_TUNEL, analista: 'Vinicius Floriano', api_nome: 'Bradesco' },
            { id: 'mcdonalds', nome: "McDonald's", col_id: 'SIGLA', status_pool: STATUS_COM_CGNAT_TUNEL, analista: 'Vinicius Floriano', api_nome: "McDonald's" },
            { id: 'l2l', nome: 'L2L (LAN-to-LAN)', col_id: 'CI', status_pool: STATUS_COM_TUNEL, analista: 'Pedro Cavalcanti', api_nome: 'L2L (LAN-to-LAN)' },
            { id: 'div_vivo', nome: 'Diversos', col_id: 'CI', status_pool: STATUS_BASE, analista: 'Pedro Cavalcanti', api_nome: 'Diversos' },
        ]
    },
    {
        id: 'algar', nome: 'Algar', cor: 'algar',
        projetos: [
            { id: 'escolas', nome: 'Escolas Conectadas', col_id: 'CI', status_pool: STATUS_COM_TUNEL, analista: 'Vinicius Floriano', api_nome: 'Escolas Conectadas' },
        ]
    },
    {
        id: 'outros', nome: 'Outros', cor: 'outros', sem_detalhe: true,
        projetos: [
            { id: 'ngo', nome: 'NGO - Não Geográfico', api_nome: 'NGO - Não Geográfico' },
            { id: 'reincidencias', nome: 'Reincidências', api_nome: 'Reincidências' },
        ]
    },
];

// ── HELPERS DA API ─────────────────────────────────────────
function getTotalOp(dadosResumo, opId) {
    if (!dadosResumo) return null;
    const op = dadosResumo[opId];
    return (op && op.total != null) ? op.total : null;
}

function getProjDataApi(dadosResumo, opId, projetoId) {
    if (!dadosResumo || !dadosResumo[opId] || !dadosResumo[opId].projetos) return null;
    return dadosResumo[opId].projetos.find(p => p.id === projetoId) || null;
}

// ── FETCH PRINCIPAL ────────────────────────────────────────
function carregarDados() {
    fetch('/projetos/api/dashboard-resumo/')
        .then(r => {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(data => {
            if (data.ok === false) throw new Error('Resumo OTRS indisponível');
            _dadosResumo = data;
            renderKPIs(data);
            renderOperadoras(data);
            renderGraficos(data);
            renderDestaquesSLA(data);
        })
        .catch(err => {
            console.error('[RESUMO] Erro ao carregar dados:', err);
            const strip = document.getElementById('kpi-strip');
            if (!strip) return;
            if (_dadosResumo) {
                strip.querySelector('.kpi-card__label').textContent = 'OTRS · atualização falhou';
                strip.title = 'Exibindo a última leitura: ' + _dadosResumo.atualizado_em;
            } else {
                strip.innerHTML = '<div class="kpi-card"><div class="kpi-card__label">OTRS indisponível</div><div class="kpi-card__value">—</div></div>';
            }
        });
}

// ── RENDERIZAÇÃO: KPIs GIGANTES DO TOPO ────────────────────
function renderKPIs(data) {
    const container = document.getElementById('kpi-strip');
    if (!container) return;
    container.title = data.atualizado_em ? 'Leitura OTRS: ' + data.atualizado_em : '';

    const total = data.total ?? '—';
    const emAberto = data.total_em_aberto ?? '—';
    const resolvidos = data.resolvidos ?? '—';
    const atrasados = data.atrasados ?? 0;

    container.innerHTML = `
        <div class="kpi-card kpi-card--total">
            <div class="kpi-card__label">NOC - ATACADO</div>
            <div class="kpi-card__value" id="kpi-total">${total}</div>
        </div>
        <div class="kpi-card kpi-card--aberto">
            <div class="kpi-card__label">Em Aberto · NOC - ATACADO</div>
            <div class="kpi-card__value">${emAberto}</div>
        </div>
        <div class="kpi-card kpi-card--resolv">
            <div class="kpi-card__label">Resolvidos</div>
            <div class="kpi-card__value">${resolvidos}</div>
        </div>
        <div class="kpi-card kpi-card--sla">
            <div class="kpi-card__label">SLA Atrasado</div>
            <div class="kpi-card__value">${atrasados}</div>
        </div>
    `;
}

// ── RENDERIZAÇÃO: GRID DE OPERADORAS E PROJETOS ────────────
function renderOperadoras(data) {
    const container = document.getElementById('operadoras-container');
    if (!container) return;

    container.innerHTML = ESTRUTURA.map(op => {
        const totalOp = getTotalOp(data, op.id);

        const cardsHtml = op.projetos.map(proj => {
            const projDataApi = getProjDataApi(data, op.id, proj.id);
            const total = projDataApi?.valor ?? '—';

            return `
            <div class="projeto-card projeto-card--${op.cor}" title="${escapeHtml(proj.nome)}">
                <div class="projeto-card__name">${escapeHtml(proj.nome)}</div>
                <div class="projeto-card__num">${total}</div>
            </div>`;
        }).join('');

        return `
        <div class="operadora-section" id="op-${op.id}">
            <div class="operadora-header">
                <div class="operadora-title op-title-${op.cor}">${op.nome}</div>
                <div class="operadora-total-text" title="Chamados únicos nos projetos mapeados; métricas adicionais estão na API ATACADO">${totalOp ?? '—'} Chamados</div>
            </div>
            <div class="projetos-grid" id="grid-${op.id}">
                ${cardsHtml}
            </div>
        </div>`;
    }).join('');
}

// ── RENDERIZAÇÃO: DESTAQUES SLA LATERAL ────────────────────
function renderDestaquesSLA(data) {
    const el = document.getElementById('sla-highlight-list');
    if (!el) return;

    const itens = [];
    ESTRUTURA.filter(op => !op.sem_detalhe).forEach(op => {
        op.projetos.forEach(proj => {
            const projDataApi = getProjDataApi(data, op.id, proj.id);
            const atrasados = projDataApi ? (projDataApi.atrasados || 0) : 0;
            if (atrasados > 0) {
                itens.push({ nome: proj.nome, opNome: op.nome, atrasados });
            }
        });
    });

    itens.sort((a, b) => b.atrasados - a.atrasados);

    // Mostra o top 6 para não quebrar a tela (sem scroll)
    const top = itens.slice(0, 6);

    if (top.length === 0) {
        el.innerHTML = `
            <div class="sla-highlight-empty">
                Tudo no prazo
                <span>Nenhum chamado fora do SLA.</span>
            </div>`;
        return;
    }

    el.innerHTML = top.map(it => `
        <div class="sla-highlight-item">
            <div class="sla-highlight-item__name">
                ${escapeHtml(it.nome)}
                <span class="sla-highlight-item__op">${escapeHtml(it.opNome)}</span>
            </div>
            <div class="sla-highlight-item__count">${it.atrasados}</div>
        </div>
    `).join('');
}

// ── RENDERIZAÇÃO: GRÁFICO (CHART.JS) ───────────────────────
function renderGraficos(data) {
    const opLabels = [];
    const opAbertos = [];
    const opResolv = [];

    // Ignoramos a categoria "Outros" no gráfico de barras principal
    ESTRUTURA.filter(op => !op.sem_detalhe).forEach(op => {
        opLabels.push(op.nome);
        opAbertos.push(getTotalOp(data, op.id));
        opResolv.push((data[op.id] && data[op.id].resolvidos) ? data[op.id].resolvidos : 0);
    });

    const ctxOp = document.getElementById('chartOp');
    if (!ctxOp) return;

    // Cores lidas das variáveis de tema do base.css, para acompanhar
    // automaticamente o modo claro/escuro selecionado pelo usuário.
    const corTextoMuted = getCssVar('--text-muted', '#8A8D93');
    const corAberto = getCssVar('--algar-color', '#0EA5E9');
    const corResolvido = getCssVar('--sla-ok', '#16A34A');
    const corSurface = getCssVar('--bg-elevated', '#202020');
    const corBorda = getCssVar('--border-strong', 'rgba(255,255,255,0.13)');
    const corTextoPrimario = getCssVar('--text-primary', '#EDEDED');

    Chart.defaults.color = corTextoMuted;
    Chart.defaults.font.family = getCssVar('--font-body', "'Plus Jakarta Sans', sans-serif");

    if (_chartInstance) {
        _chartInstance.data.labels = opLabels;
        _chartInstance.data.datasets[0].data = opAbertos;
        _chartInstance.data.datasets[1].data = opResolv;
        _chartInstance.update();
        return;
    }

    _chartInstance = new Chart(ctxOp, {
        type: 'bar',
        data: {
            labels: opLabels,
            datasets: [
                {
                    label: 'Em Aberto',
                    data: opAbertos,
                    backgroundColor: corAberto,
                    borderRadius: 6,
                    borderSkipped: false
                },
                {
                    label: 'Resolvidos',
                    data: opResolv,
                    backgroundColor: corResolvido,
                    borderRadius: 6,
                    borderSkipped: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: corSurface,
                    titleColor: corTextoPrimario,
                    bodyColor: corTextoPrimario,
                    titleFont: { size: 14 },
                    bodyFont: { size: 13 },
                    padding: 12,
                    borderColor: corBorda,
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { weight: 'bold' } }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(128, 128, 128, 0.12)' },
                    border: { display: false }
                }
            }
        }
    });

    const legendEl = document.getElementById('legend-op');
    if (legendEl) {
        legendEl.innerHTML = `
            <span><i style="background:${corAberto}; display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:5px; vertical-align:middle;"></i>Abertos</span>
            <span><i style="background:${corResolvido}; display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:5px; vertical-align:middle;"></i>Resolvidos</span>
        `;
    }
}

// ── INICIALIZAÇÃO ──────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    carregarDados();
    // Atualiza o painel da TV a cada 60 segundos
    setInterval(carregarDados, 60000);
});
