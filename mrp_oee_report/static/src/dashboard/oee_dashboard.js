/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const RANGES = [
    ["today", "Hoy"],
    ["yesterday", "Ayer"],
    ["7d", "7 días"],
    ["30d", "30 días"],
    ["month", "Mes"],
    ["custom", "Rango"],
];
const STATUS_LABEL = { good: "En meta", warn: "Cerca de la meta", bad: "Bajo la meta", none: "Sin dato" };
const STATUS_ICON = { good: "fa-check-circle", warn: "fa-exclamation-circle", bad: "fa-times-circle", none: "fa-minus-circle" };

export class OeeDashboard extends Component {
    static template = "mrp_oee_report.OeeDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.ranges = RANGES;
        this.state = useState({
            loading: true,
            error: false,
            data: null,
            tab: "machines",
            unit: "h",
            sortKey: "oee",
            sortAsc: true,
            f: {
                range: "today",
                date_from: "",
                date_to: "",
                tag_id: "",
                workcenter_id: "",
                shift: "",
                search: "",
                planned_only: false,
            },
        });
        onWillStart(() => this.load());
    }

    // ------------------------------------------------------------------ data
    params() {
        const f = this.state.f;
        return {
            range: f.range,
            date_from: f.date_from || false,
            date_to: f.date_to || false,
            tag_ids: f.tag_id ? [parseInt(f.tag_id)] : [],
            workcenter_ids: f.workcenter_id ? [parseInt(f.workcenter_id)] : [],
            shift: f.shift || false,
            search: f.search || "",
            planned_only: f.planned_only,
        };
    }

    async load() {
        this.state.loading = true;
        this.state.error = false;
        try {
            this.state.data = await this.orm.call("mrp.oee.dashboard", "get_dashboard_data", [this.params()]);
            const r = this.state.data.range;
            if (this.state.f.range !== "custom") {
                this.state.f.date_from = r.from;
                this.state.f.date_to = r.to;
            }
        } catch (e) {
            this.state.error = (e && e.message) || "No se pudieron cargar los datos.";
        }
        this.state.loading = false;
    }

    setRange(key) {
        this.state.f.range = key;
        if (key !== "custom") {
            this.load();
        }
    }
    onDate(ev, which) {
        this.state.f[which] = ev.target.value;
        this.state.f.range = "custom";
        if (this.state.f.date_from && this.state.f.date_to) {
            this.load();
        }
    }
    onSelect(ev, key) {
        this.state.f[key] = ev.target.value;
        if (key === "tag_id") {
            this.state.f.workcenter_id = "";
        }
        this.load();
    }
    onSearchKey(ev) {
        if (ev.key === "Enter") {
            this.state.f.search = ev.target.value;
            this.load();
        }
    }
    togglePlanned(ev) {
        this.state.f.planned_only = ev.target.checked;
        this.load();
    }
    clearFilters() {
        Object.assign(this.state.f, { tag_id: "", workcenter_id: "", shift: "", search: "", planned_only: false });
        this.load();
    }
    pickMachine(id) {
        this.state.f.workcenter_id = String(id);
        this.load();
    }
    openLines() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Líneas de OEE",
            res_model: "mrp.oee.line",
            views: [[false, "list"], [false, "pivot"]],
            domain: this.state.data.domain,
            target: "current",
        });
    }
    setTab(t) {
        this.state.tab = t;
    }
    sortBy(key) {
        if (this.state.sortKey === key) {
            this.state.sortAsc = !this.state.sortAsc;
        } else {
            this.state.sortKey = key;
            this.state.sortAsc = key === "oee" || key === "d" || key === "r" || key === "c";
        }
    }

    // ------------------------------------------------------------ getters
    get d() {
        return this.state.data;
    }
    get k() {
        return this.state.data.kpi;
    }
    get filteredWorkcenters() {
        const tag = parseInt(this.state.f.tag_id);
        const all = this.d.options.workcenters;
        return tag ? all.filter((w) => w.tag_ids.includes(tag)) : all;
    }
    get tabRows() {
        const t = this.state.tab;
        const rows = t === "machines" ? this.d.machines : this.d.tabs[t] || [];
        const key = this.state.sortKey;
        const dir = this.state.sortAsc ? 1 : -1;
        const val = (r) => {
            if (key === "name") {
                return (r.code || r.name || "").toString();
            }
            if (key === "registrado") {
                return r.min.registrado;
            }
            const v = r[key];
            return v === null || v === undefined ? (this.state.sortAsc ? Infinity : -Infinity) : v;
        };
        return [...rows].sort((a, b) => {
            const x = val(a);
            const y = val(b);
            if (typeof x === "string") {
                return x.localeCompare(y) * dir;
            }
            return (x - y) * dir;
        });
    }
    get waterfall() {
        const m = this.k.min;
        const steps = [];
        const hasTurno = this.k.min_turno > 0;
        const top = hasTurno ? Math.max(this.k.min_turno, m.registrado) : m.registrado;
        if (hasTurno) {
            steps.push({ label: "Duración de turnos", sub: "según el calendario del CT", kind: "total", start: 0, value: this.k.min_turno });
            steps.push({ label: "Sin registrar", sub: "tiempo de turno sin línea de tiempo", kind: "neutral-loss", start: m.registrado, value: this.k.min_sin_registrar });
        }
        steps.push({ label: "Tiempo registrado", sub: "suma del seguimiento de tiempo", kind: "total", start: 0, value: m.registrado });
        steps.push({ label: "Paradas autorizadas", sub: "setup, cambio de molde o color, purga", kind: "authorized", start: m.cargado, value: m.autorizada });
        steps.push({ label: "Tiempo cargado", sub: "lo que se debió producir · base de la Disponibilidad", kind: "total", start: 0, value: m.cargado });
        steps.push({ label: "Paradas no programadas", sub: "fallas, falta de material o de operario", kind: "unplanned", start: m.operando, value: m.no_programada });
        steps.push({ label: "Tiempo operando", sub: "la máquina estaba corriendo", kind: "total", start: 0, value: m.operando });
        if (m.sin_estandar > 0.5) {
            steps.push({ label: "Sin ciclo estándar", sub: "no entra al Rendimiento", kind: "neutral-loss", start: m.operando - m.sin_estandar, value: m.sin_estandar });
        }
        const vel = Math.max(m.velocidad, 0);
        steps.push({ label: "Pérdida de velocidad", sub: "corrió más lento que el estándar", kind: "speed", start: m.valioso + m.calidad, value: vel });
        steps.push({ label: "Pérdida de calidad", sub: "tiempo que se fue en averías", kind: "quality", start: m.valioso, value: m.calidad });
        steps.push({ label: "Tiempo valioso", sub: "convertido en producto bueno", kind: "good", start: 0, value: m.valioso });
        return steps.map((s) => ({
            ...s,
            left: top ? (100 * Math.max(s.start, 0)) / top : 0,
            width: top ? Math.max((100 * s.value) / top, s.value > 0 ? 0.4 : 0) : 0,
            share: top ? Math.round((100 * s.value) / top) : 0,
        }));
    }
    get lostMachines() {
        const rows = this.d.machines.filter((r) => r.min.perdido > 0).slice(0, 10);
        const max = Math.max(1, ...rows.map((r) => r.min.perdido));
        return rows.map((r) => {
            const seg = (v) => (100 * Math.max(v, 0)) / max;
            return {
                ...r,
                segs: [
                    { kind: "unplanned", w: seg(r.min.no_programada), v: r.min.no_programada, label: "Paradas no programadas" },
                    { kind: "speed", w: seg(r.min.velocidad), v: Math.max(r.min.velocidad, 0), label: "Velocidad" },
                    { kind: "quality", w: seg(r.min.calidad), v: r.min.calidad, label: "Calidad (averías)" },
                ].filter((s) => s.w > 0),
            };
        });
    }
    get shiftBars() {
        const rows = this.d.shifts;
        const max = Math.max(100, ...rows.map((r) => r.oee || 0));
        return rows.map((r) => ({ ...r, h: r.oee === null ? 0 : (100 * r.oee) / max }));
    }
    get targetLine() {
        const max = Math.max(100, ...this.d.shifts.map((r) => r.oee || 0));
        return (100 * this.k.target) / max;
    }
    useBar(r) {
        const m = r.min;
        const tot = m.registrado || 1;
        const p = (v) => (100 * Math.max(v, 0)) / tot;
        return [
            { kind: "good", w: p(m.valioso), label: "Valioso", v: m.valioso },
            { kind: "speed", w: p(m.velocidad), label: "Velocidad", v: m.velocidad },
            { kind: "quality", w: p(m.calidad), label: "Calidad", v: m.calidad },
            { kind: "unplanned", w: p(m.no_programada), label: "No programadas", v: m.no_programada },
            { kind: "authorized", w: p(m.autorizada), label: "Autorizadas", v: m.autorizada },
        ].filter((s) => s.w > 0.2);
    }
    paretoMax(rows) {
        return Math.max(1, ...rows.map((r) => r.value));
    }

    // ------------------------------------------------------------ format
    t(min) {
        if (min === null || min === undefined) {
            return "—";
        }
        if (this.state.unit === "min") {
            return `${Math.round(min).toLocaleString("es-CO")} min`;
        }
        const sign = min < 0 ? "-" : "";
        const a = Math.round(Math.abs(min));
        return `${sign}${Math.floor(a / 60)}:${String(a % 60).padStart(2, "0")} h`;
    }
    pct(v) {
        return v === null || v === undefined ? "—" : `${Math.round(v)}%`;
    }
    pct1(v) {
        return v === null || v === undefined
            ? "—"
            : `${v.toLocaleString("es-CO", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
    }
    num(v) {
        return v === null || v === undefined ? "—" : Math.round(v).toLocaleString("es-CO");
    }
    money(v) {
        return v ? `$${Math.round(v).toLocaleString("es-CO")}` : "—";
    }
    statusLabel(s) {
        return STATUS_LABEL[s] || "";
    }
    statusIcon(s) {
        return STATUS_ICON[s] || "";
    }
}

registry.category("actions").add("mrp_oee_dashboard", OeeDashboard);
