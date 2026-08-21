# -*- coding: utf-8 -*-
import io
import base64
import math
import calendar
from odoo import models, fields, _
from odoo.exceptions import UserError

# Plantillas de registro (constantes byte a byte, validadas contra archivo CGUNO real)
BASE02 = '0200000000000000000      0100  00000000000000000        00000000000                   000000000000        000000000                     00    0 00000  00000000      E0S000      CCF00 0000000000000000000000000000000000000000000000000000000.000000000000000000000000000000000000000000000000000000000000000000000.00000000000000000000000               000000000               0000000000.00000000000000000000000000.000000000000000.000000000000000.000000000000000.000000000000000.00000000000000                  014-11 0 00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000                                        000000000000          0000000'
HDR = '0100001PROIMPO SAS                                                                                                                                                                                             NI890319790       0E                    U                                                  14-11 2026-062026-070000000000          002280007518669020100'
TRL = '060000114-11 000000089090379050000000000000               000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'

# Clase de riesgo ARL -> (tarifa, codigo pos 398, clase pos 513)
# Centro de trabajo ARL (codigo CGUNO 01-05) -> (tarifa, pos 398, clase pos 513)
ARL_MAP = {
    '1': (0.00522, '1', '1'),   # 01 Riesgo minimo
    '2': (0.01044, '2', '2'),   # 02 Riesgo bajo
    '3': (0.00000, '3', '0'),   # 03 Tarifa 0%
    '4': (0.04350, '4', '4'),   # 04 Riesgo alto
    '5': (0.02436, '5', '3'),   # 05 Centro 2.436 alto
}

# Novedad PILA -> (posicion 1-indexed, caracter, subsistemas que cotizan)
#   subsistemas: p=pension  s=salud  a=arl  c=caja   (parafiscales siguen la regla alto ingreso 'f')
# Validado byte a byte contra archivo real de CGUNO (PPI...02).
_PILA_NOV_POS = {
    'VAC': (149, 'X', 'psac'),   # vacaciones
    'LR':  (149, 'L', 'psc'),    # licencia remunerada (incluye dia de la familia)
    'IGE': (147, 'X', 'ps'),     # incapacidad general
    'IRL': (153, '2', 'ps'),     # incapacidad riesgos laborales: pos 153='2' (validado vs julio)
    'LMA': (148, 'X', 'psc'),    # licencia de maternidad
    'SLN': (146, 'X', 'p'),      # suspension / lic. no remunerada: cotiza SOLO pension (validado vs junio)
}


def _put(buf, start, ln, val, pad='0', right=True):
    """Coloca val en buf en posicion 1-indexed start, longitud ln."""
    s = str(val)
    s = s.rjust(ln, pad)[-ln:] if right else s.ljust(ln, pad)[:ln]
    buf[start - 1:start - 1 + ln] = list(s)


def _ap(v):
    """Aproximacion PILA: al multiplo de 100 superior; guarda valor/100."""
    return int(math.ceil(v / 100.0)) if v > 0 else 0


def _split_nombre(nombre):
    """'APELLIDOS, NOMBRES' -> (ap1, ap2, nom1, nom2)."""
    nombre = (nombre or '').strip().upper()
    if ',' in nombre:
        ape, nom = nombre.split(',', 1)
    else:
        # sin coma: se asume 'AP1 AP2 NOM1 NOM2'
        parts = nombre.split()
        ape = ' '.join(parts[:2])
        nom = ' '.join(parts[2:])
    ape = ape.split()
    nom = nom.split()
    ap1 = ape[0] if ape else ''
    ap2 = ' '.join(ape[1:]) if len(ape) > 1 else ''
    no1 = nom[0] if nom else ''
    no2 = ' '.join(nom[1:]) if len(nom) > 1 else ''
    return ap1, ap2, no1, no2



def _empresa_propia_param(env):
    return env['ir.config_parameter'].sudo().get_param(
        'proimpo_nomina.empresa_propia', 'PROIMPO SAS')


def _dom_empresa_propia(env):
    """Leaf de dominio: procesar solo empleados de la empresa propia (excluye temporales)."""
    if 'x_studio_contrato_con' in env['hr.employee']._fields:
        return [('employee_id.x_studio_contrato_con', '=', _empresa_propia_param(env))]
    return []


def _es_empleado_propio(emp):
    if 'x_studio_contrato_con' not in emp.env['hr.employee']._fields:
        return True
    return emp.x_studio_contrato_con == _empresa_propia_param(emp.env)


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _pila_reg02(self, seq, d, dias=None, ibc=None, nov=None, sub='psacf',
                    ing=False, ret=False):
        """Construye un registro tipo 02 (693). Si se pasa un segmento (dias/ibc/nov/sub)
        genera la linea de esa novedad; si no, la linea consolidada del empleado."""
        e = d['emp']
        ct = d['contract']
        company = ct.company_id or self.env.company
        smmlv = company.smmlv_value or 1750905.0

        ibc = int(round(d['ibc'] if ibc is None else ibc))
        dias = min(int(round(d['dias'] if dias is None else dias)), 30)
        wage = ct.wage or 0.0
        lectiva = ct.pila_etapa_aprendiz == 'lectiva'
        pensionado = bool(ct.pila_pensionado)
        alto_ingreso = wage >= 10 * smmlv

        buf = list(BASE02)

        # Zona de novedades (137-149): el operador exige ESPACIO cuando no hay novedad
        # (no '0'). Se limpia aqui y luego se ponen los flags que correspondan.
        _put(buf, 137, 13, '', right=False, pad=' ')

        # --- Identificacion ---
        _put(buf, 3, 5, seq)
        tipodoc = (getattr(e, 'l10n_latam_document_type_id', False) and
                   e.l10n_latam_document_type_id.l10n_co_document_code) or 'CC'
        tipodoc = {'rc': 'RC', 'ti': 'TI', 'cc': 'CC', 'ce': 'CE', 'pa': 'PA',
                   'national_citizen_id': 'CC'}.get(str(tipodoc).lower(), 'CC')
        _put(buf, 8, 2, tipodoc, right=False, pad=' ')
        _put(buf, 10, 16, (e.identification_id or '').strip(), right=False, pad=' ')

        # --- Cotizante ---
        tcot = (ct.type_worker_id.code if ct.type_worker_id else '01') or '01'
        if lectiva:
            tcot = '19'
        _put(buf, 26, 2, tcot)
        subt = (ct.subtype_worker_id.code if ct.subtype_worker_id else '00') or '00'
        _put(buf, 28, 2, subt)

        # --- Municipio y nombres ---
        muni = (ct.pila_municipio_code or '').strip()
        if len(muni) > 5:            # DANE debe ser 5 (depto 2 + municipio 3)
            muni = muni[:2] + muni[-3:]
        _put(buf, 32, 5, muni)
        ap1, ap2, no1, no2 = _split_nombre(e.name)
        _put(buf, 37, 20, ap1, right=False, pad=' ')
        _put(buf, 57, 30, ap2, right=False, pad=' ')
        _put(buf, 87, 20, no1, right=False, pad=' ')
        _put(buf, 107, 30, no2, right=False, pad=' ')

        # --- Novedades ---
        if ing:
            _put(buf, 137, 1, 'X', right=False, pad=' ')
        if ret:
            _put(buf, 138, 1, 'X', right=False, pad=' ')
        if nov:
            npos, nchar = nov
            _put(buf, npos, 1, nchar, right=False, pad=' ')
        else:
            # Linea base/consolidada: marca de cotizante con IBC variable
            variable = d.get('devsal', 0.0) > 0 or ibc > int(round(wage / 30.0 * dias))
            if variable:
                _put(buf, 145, 1, 'X', right=False, pad=' ')

        # --- Entidades ---
        _put(buf, 154, 6, (ct.pila_afp_code or '').strip(), right=False, pad=' ')
        _put(buf, 166, 6, (ct.pila_eps_code or '').strip(), right=False, pad=' ')
        ccf = (ct.pila_ccf_code or '').strip()
        _put(buf, 178, 5, ccf, right=False, pad=' ')

        # --- Dias (4 subsistemas x 2) ---
        _put(buf, 184, 8, ('%02d' % dias) * 4, right=False)

        # --- Salario basico + tipo (V variable / F fijo) ---
        _put(buf, 193, 8, int(round(wage)))
        tipo_sal = 'F' if (dias == 30 and ibc == int(round(wage))) else 'V'
        _put(buf, 201, 1, tipo_sal, right=False)

        # --- IBC x4 ---
        for st in (202, 211, 220, 229):
            _put(buf, st, 9, ibc)

        # --- Pension ---
        if 'p' in sub and not (pensionado or lectiva):
            _put(buf, 240, 2, '16')
            _put(buf, 247, 5, _ap(ibc * 0.16))
        else:
            _put(buf, 240, 2, '00')
            _put(buf, 247, 5, 0)

        # --- Salud ---
        if 's' in sub:
            rate_s = 0.125 if alto_ingreso else 0.04
            _put(buf, 310, 3, '%03d' % int(round(rate_s * 1000)))
            _put(buf, 317, 5, _ap(ibc * rate_s))

        # --- ARL ---
        tarifa, c398, c513 = ARL_MAP.get(ct.pila_arl_class or '5', ARL_MAP['5'])
        if 'a' in sub:
            _put(buf, 384, 4, '%04d' % int(round(tarifa * 100000)))
            _put(buf, 398, 1, c398)
            _put(buf, 513, 1, c513)
            _put(buf, 402, 4, _ap(ibc * tarifa))

        # --- Caja de compensacion ---
        if 'c' in sub and ccf and not lectiva:
            _put(buf, 411, 1, '4')
            _put(buf, 417, 5, _ap(ibc * 0.04))
        else:
            _put(buf, 411, 1, '0')
            _put(buf, 417, 5, 0)

        # --- SENA / ICBF (solo linea base con alto ingreso) ---
        if 'f' in sub and alto_ingreso and not lectiva:
            _put(buf, 427, 1, '2')
            _put(buf, 434, 4, _ap(ibc * 0.02))
            _put(buf, 443, 1, '3')
            _put(buf, 449, 5, _ap(ibc * 0.03))
        else:
            _put(buf, 427, 1, '0')
            _put(buf, 434, 4, 0)
            _put(buf, 443, 1, '0')
            _put(buf, 449, 5, 0)

        # --- Campos de control ---
        _put(buf, 506, 1, 'S', right=False)
        _put(buf, 515, 110, '', right=False, pad=' ')
        _put(buf, 666, 11, int(round(dias * 22.0 / 3.0)))
        centro = (ct.pila_centro_trabajo or company.pila_centro_trabajo_def or '').strip()
        _put(buf, 687, 7, centro, right=False, pad=' ')

        return ''.join(buf)

    def _pila_generar_plano(self, mes_ini):
        """Consolida el mes por empleado y genera el archivo PILA con multilinea:
        una linea base trabajada + un renglon por cada novedad (VAC, LR, IGE, IRL,
        LMA, SLN), con sus dias, IBC y subsistemas que cotizan."""
        import calendar as _cal
        company = self[0].company_id or self.env.company
        y, m = mes_ini.year, mes_ini.month
        last = fields.Date.to_date('%04d-%02d-%02d' % (y, m, _cal.monthrange(y, m)[1]))

        emp = {}
        for s in self:
            e = s.employee_id
            d = emp.setdefault(e.id, {
                'emp': e, 'contract': s.contract_id, 'ibc': 0.0, 'dias': 0.0,
                'devsal': 0.0, 'slip': s,
            })
            d['ibc'] += s._pila_line('IBC') + s._pila_line('IBCAPR')
            d['dias'] += s._dias_cotizados_pila()
            d['devsal'] += sum(s.line_ids.filtered(
                lambda l: l.category_id.code == 'DEVSAL').mapped('total'))
            if s.contract_id:
                d['contract'] = s.contract_id

        regs = []
        seq = 0
        for eid in sorted(emp, key=lambda k: (emp[k]['emp'].name or '')):
            d = emp[eid]
            ct = d['contract']
            total_ibc = int(round(d['ibc']))
            # Novedad de ingreso / retiro en el mes
            ing = bool(ct and ct.date_start and ct.date_start.year == y and ct.date_start.month == m)
            ret = bool(ct and ct.date_end and ct.date_end.year == y and ct.date_end.month == m)

            # Segmentacion de dias por novedad
            seg = d['slip']._pila_segmentos(d['emp'], ct, mes_ini, last)
            novs = [(k, int(round(seg.get(k, 0)))) for k in
                    ('SLN', 'IGE', 'IRL', 'LMA', 'VAC', 'LR') if int(round(seg.get(k, 0))) > 0]

            if not novs:
                # Sin novedades: una sola linea consolidada
                seq += 1
                regs.append(self._pila_reg02(seq, d, ing=ing, ret=ret))
                continue

            # Con novedades: IBC del salario base prorrateado por dia
            variable = max(d.get('devsal', 0.0), 0.0)
            salario_mes = max(total_ibc - variable, 0.0)
            base_dia = salario_mes / 30.0
            usados_dias = 0
            usados_ibc = 0
            for k, dd in novs:
                pos, char, sub = _PILA_NOV_POS[k]
                seg_ibc = int(round(base_dia * dd))
                usados_dias += dd
                usados_ibc += seg_ibc
                seq += 1
                regs.append(self._pila_reg02(seq, d, dias=dd, ibc=seg_ibc,
                                             nov=(pos, char), sub=sub))
            # Linea base trabajada: dias e IBC restantes (absorbe la parte variable)
            work_dias = max(30 - usados_dias, 0)
            work_ibc = max(total_ibc - usados_ibc, 0)
            if work_dias > 0 or work_ibc > 0:
                seq += 1
                regs.append(self._pila_reg02(seq, d, dias=work_dias, ibc=work_ibc,
                                             sub='psacf', ing=ing, ret=ret))

        n_cot = len(emp)
        per_cot = '%04d-%02d' % (y, m)
        my = m + 1; yy = y
        if my > 12:
            my = 1; yy += 1
        per_pago = '%04d-%02d' % (yy, my)

        tot_cotiz = 0
        for r in regs:
            for st, ln in ((247, 5), (317, 5), (402, 4), (417, 5), (434, 4), (449, 5)):
                tot_cotiz += int(r[st - 1:st - 1 + ln] or '0') * 100

        hb = list(HDR)
        _put(hb, 305, 7, per_cot, right=False, pad=' ')
        _put(hb, 312, 7, per_pago, right=False, pad=' ')
        _put(hb, 339, 5, n_cot)
        header = ''.join(hb)

        tb = list(TRL)
        _put(tb, 20, 12, tot_cotiz)
        trailer = ''.join(tb)

        return header + '\n' + '\n'.join(regs) + '\n' + trailer + '\n'


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    def action_generar_pila_plano(self):
        """Genera el archivo plano PILA del MES de causacion del lote (ambas quincenas)."""
        self.ensure_one()
        y, m = self.date_start.year, self.date_start.month
        first = fields.Date.to_date('%04d-%02d-01' % (y, m))
        last = fields.Date.to_date('%04d-%02d-%02d' % (y, m, calendar.monthrange(y, m)[1]))
        slips = self.env['hr.payslip'].search([
            ('state', 'in', ('done', 'paid')),
            ('date_from', '<=', last), ('date_to', '>=', first),
        ] + _dom_empresa_propia(self.env))
        if not slips:
            raise UserError(_("No hay recibos confirmados en el mes %04d-%02d." % (y, m)))
        contenido = slips._pila_generar_plano(first)
        nombre = 'PILA_%04d%02d.txt' % (y, m)
        att = self.env['ir.attachment'].create({
            'name': nombre, 'type': 'binary',
            'datas': base64.b64encode(contenido.encode('latin-1')),
            'mimetype': 'text/plain',
        })
        return {'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % att.id, 'target': 'self'}


class ResCompany(models.Model):
    _inherit = 'res.company'

    pila_centro_trabajo_def = fields.Char(
        string="Centro de trabajo PILA (def.)",
        help="Codigo de centro de trabajo/actividad por defecto para la PILA (pos 687-693). "
             "Se puede sobreescribir por contrato.")
