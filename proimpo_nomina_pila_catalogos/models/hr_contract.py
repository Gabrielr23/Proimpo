# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrContract(models.Model):
    _inherit = 'hr.contract'

    # Desplegables (Many2one). Al elegirlos, rellenan el codigo Char que YA usa el plano.
    pila_eps_id = fields.Many2one('pila.entidad', string='EPS (salud)',
                                  domain="[('tipo','=','eps')]")
    pila_afp_id = fields.Many2one('pila.entidad', string='AFP (pensión)',
                                  domain="[('tipo','=','afp')]")
    pila_arl_id = fields.Many2one('pila.entidad', string='ARL',
                                  domain="[('tipo','=','arl')]")
    pila_ccf_id = fields.Many2one('pila.entidad', string='Caja de compensación',
                                  domain="[('tipo','=','ccf')]")
    pila_municipio_id = fields.Many2one('pila.municipio', string='Municipio de labor (DANE)')
    pila_arl_clase_id = fields.Many2one('pila.arl.clase',
                                        string='Centro de trabajo / clase riesgo ARL')

    # Mapa desplegable -> campo de codigo existente (que lee el plano)
    _PILA_MAP = {
        'pila_eps_id': ('pila_eps_code', 'code'),
        'pila_afp_id': ('pila_afp_code', 'code'),
        'pila_arl_id': ('pila_arl_code', 'code'),
        'pila_ccf_id': ('pila_ccf_code', 'code'),
        'pila_municipio_id': ('pila_municipio_code', 'code'),
        'pila_arl_clase_id': ('pila_arl_class', 'code'),
    }

    def _pila_sync_codigos(self, vals):
        """Devuelve vals con los codigos Char actualizados desde los desplegables."""
        out = dict(vals)
        for m2o, (char_f, attr) in self._PILA_MAP.items():
            if m2o in vals:
                rec = self.env[self._fields[m2o].comodel_name].browse(vals[m2o]) if vals[m2o] else False
                out[char_f] = getattr(rec, attr) if rec else out.get(char_f)
        return out

    @api.onchange('pila_eps_id', 'pila_afp_id', 'pila_arl_id', 'pila_ccf_id',
                  'pila_municipio_id', 'pila_arl_clase_id')
    def _onchange_pila_desplegables(self):
        for c in self:
            for m2o, (char_f, attr) in self._PILA_MAP.items():
                rec = c[m2o]
                if rec:
                    setattr(c, char_f, getattr(rec, attr))

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._pila_sync_codigos(v) for v in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if any(k in vals for k in self._PILA_MAP):
            vals = self._pila_sync_codigos(vals)
        return super().write(vals)
