# -*- coding: utf-8 -*-
import base64
import io
from datetime import date, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

# Recargo dominical/festivo vigente segun la fecha (reforma laboral Ley 2466/2025):
# 75% (hasta jun-2025) -> 80% (jul-2025) -> 90% (jul-2026) -> 100% (jul-2027).
def recargo_dominical_pct(fecha):
    if fecha >= date(2027, 7, 1):
        return 1.00
    if fecha >= date(2026, 7, 1):
        return 0.90
    if fecha >= date(2025, 7, 1):
        return 0.80
    return 0.75


# Parte FIJA del factor (sin dominical). A los codigos dom/festivo se les suma el
# recargo dominical vigente segun la fecha del recibo.
BASE_FIJA = {
    'HED': 1.25,    # 1 + 0.25 extra diurna
    'HEN': 1.75,    # 1 + 0.75 extra nocturna
    'HRN': 0.35,    # 0.35 recargo nocturno
    'HEDDF': 1.25,  # 1 + 0.25 + dominical
    'HRDDF': 0.00,  #           dominical
    'HENDF': 1.75,  # 1 + 0.75 + dominical
    'HRNDF': 0.35,  # 0.35 +     dominical
}
LLEVA_DOMINICAL = {'HEDDF', 'HRDDF', 'HENDF', 'HRNDF'}
CODIGOS_EXTRA = list(BASE_FIJA.keys())
# Novedades que se cargan en VALOR (pesos), no en horas
CODIGOS_VALOR = ['COM', 'BON', 'BONNS']
TODOS_CODIGOS = CODIGOS_EXTRA + CODIGOS_VALOR


class CargarNovedades(models.TransientModel):
    _name = 'proimpo.cargar.novedades'
    _description = 'Cargue masivo de novedades de nómina desde Excel'

    batch_id = fields.Many2one(
        'hr.payslip.run', string='Lote de nómina', required=True,
        help="Lote (payslip run) cuyos recibos recibirán las novedades.")
    archivo = fields.Binary(string='Archivo Excel (.xlsx)', required=True)
    nombre_archivo = fields.Char(string='Nombre del archivo')
    reemplazar = fields.Boolean(
        string='Reemplazar novedades existentes de estos códigos', default=True,
        help="Si está marcado, borra las líneas previas de los códigos presentes en "
             "el archivo antes de cargar (hace el cargue repetible). Útil en pruebas.")
    recalcular = fields.Boolean(string='Recalcular recibos al terminar', default=True)
    resultado = fields.Text(string='Resultado', readonly=True)

    # ------------------------------------------------------------------
    def _divisor_hora(self, slip):
        """Divisor mensual de horas segun la fecha del recibo (reduccion de jornada)."""
        fecha = slip.date_to or date.today()
        return 220.0 if fecha < date(2026, 7, 15) else 210.0

    def _factor_hora(self, slip, codigo):
        """Factor (valor_hora x factor) segun codigo y fecha del recibo."""
        base = BASE_FIJA.get(codigo)
        if base is None:
            return 0.0
        fecha = slip.date_to or date.today()
        if codigo in LLEVA_DOMINICAL:
            return round(base + recargo_dominical_pct(fecha), 4)
        return base

    def _valor_hora(self, slip, codigo):
        """Valor por hora del concepto = wage / divisor * factor."""
        wage = slip.contract_id.wage or 0.0
        factor = self._factor_hora(slip, codigo)
        div = self._divisor_hora(slip)
        return round(wage / div * factor, 2) if (wage and div and factor) else 0.0

    def _horas_a_periodo(self, slip, horas):
        """Convierte horas a (date_start, date_end, time_start, time_end) para que
        la línea de devengado calcule quantity = horas."""
        dias = int(horas // 24)
        resto = horas - 24 * dias
        d0 = slip.date_from or slip.date_to or date.today()
        return {
            'date_start': d0,
            'date_end': d0 + timedelta(days=dias),
            'time_start': 0.0,
            'time_end': round(resto, 4),
        }

    def _rule_input(self, codigo):
        ri = self.env['hr.rule.input'].search([('code', '=', codigo)], limit=1)
        return ri

    def _buscar_empleado(self, cedula, nombre):
        Emp = self.env['hr.employee']
        emp = Emp.browse()
        if cedula:
            emp = Emp.search([('identification_id', '=', str(cedula).strip())], limit=1)
        if not emp and nombre:
            emp = Emp.search([('name', '=ilike', str(nombre).strip())], limit=1)
        return emp

    # ------------------------------------------------------------------
    def action_cargar(self):
        self.ensure_one()
        try:
            import openpyxl
        except ImportError:
            raise UserError(_("Falta la librería openpyxl en el servidor."))

        if not self.archivo:
            raise UserError(_("Adjunte el archivo Excel."))

        data = base64.b64decode(self.archivo)
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise UserError(_("El archivo está vacío."))

        # Encabezado: localizar columnas
        header = [str(c).strip().upper() if c is not None else '' for c in rows[0]]

        def col(*nombres):
            for n in nombres:
                if n in header:
                    return header.index(n)
            return None

        col_ced = col('CEDULA', 'CÉDULA', 'DOCUMENTO', 'IDENTIFICACION', 'IDENTIFICACIÓN')
        col_nom = col('NOMBRE', 'EMPLEADO', 'NOMBRE EMPLEADO')
        cols_cod = {c: header.index(c) for c in TODOS_CODIGOS if c in header}

        if not cols_cod:
            raise UserError(_("El archivo no tiene columnas de novedades reconocidas "
                              "(%s).") % ", ".join(TODOS_CODIGOS))
        if col_ced is None and col_nom is None:
            raise UserError(_("El archivo debe tener columna 'Cédula' o 'Nombre'."))

        # Precargar rule.inputs por codigo
        rule_inputs = {}
        for c in cols_cod:
            ri = self._rule_input(c)
            if not ri:
                raise UserError(_("No existe una entrada de regla (hr.rule.input) con "
                                  "código '%s'. Verifique las reglas salariales.") % c)
            rule_inputs[c] = ri

        codigos_archivo = list(cols_cod.keys())
        slips_por_empleado = {s.employee_id.id: s for s in self.batch_id.slip_ids}

        n_ok = 0
        n_lineas = 0
        errores = []
        slips_tocados = self.env['hr.payslip']

        for i, row in enumerate(rows[1:], start=2):
            cedula = row[col_ced] if col_ced is not None else None
            nombre = row[col_nom] if col_nom is not None else None
            if cedula in (None, '') and nombre in (None, ''):
                continue  # fila vacía

            emp = self._buscar_empleado(cedula, nombre)
            if not emp:
                errores.append(_("Fila %s: empleado no encontrado (%s / %s).") % (i, cedula, nombre))
                continue

            slip = slips_por_empleado.get(emp.id)
            if not slip:
                errores.append(_("Fila %s: %s no tiene recibo en el lote.") % (i, emp.name))
                continue

            # Reemplazar novedades previas de estos codigos
            if self.reemplazar:
                previas = slip.earn_ids.filtered(lambda e: e.code in codigos_archivo)
                if previas:
                    previas.unlink()

            hubo = False
            for cod in codigos_archivo:
                val = row[cols_cod[cod]]
                if val in (None, '', 0):
                    continue
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    errores.append(_("Fila %s: valor inválido en %s (%s).") % (i, cod, val))
                    continue
                if val <= 0:
                    continue

                vals = {
                    'payslip_id': slip.id,
                    'rule_input_id': rule_inputs[cod].id,
                    'name': rule_inputs[cod].name,
                }
                if cod in CODIGOS_EXTRA:
                    # val = horas -> amount = valor hora, quantity via fechas
                    vals['amount'] = self._valor_hora(slip, cod)
                    vals.update(self._horas_a_periodo(slip, val))
                else:
                    # val = valor en pesos -> amount = valor, quantity = 1
                    vals['amount'] = round(val, 2)

                if vals.get('amount', 0.0) <= 0:
                    errores.append(_("Fila %s: %s quedó con valor 0 (¿salario del contrato?).") % (i, cod))
                    continue

                self.env['l10n_co_hr_payroll.earn.line'].create(vals)
                n_lineas += 1
                hubo = True

            if hubo:
                n_ok += 1
                slips_tocados |= slip

        # Recalcular
        if self.recalcular and slips_tocados:
            for s in slips_tocados:
                try:
                    s.compute_sheet()
                except Exception as e:  # noqa: BLE001
                    errores.append(_("Recalculo %s: %s") % (s.employee_id.name, e))

        resumen = [_("Empleados con novedades: %s") % n_ok,
                   _("Líneas creadas: %s") % n_lineas]
        if errores:
            resumen.append("")
            resumen.append(_("Avisos (%s):") % len(errores))
            resumen.extend(errores[:50])
        self.resultado = "\n".join(str(x) for x in resumen)

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
