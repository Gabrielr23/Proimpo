# -*- coding: utf-8 -*-
def post_init_hook(env):
    """Mapea los contratos existentes: del codigo Char que ya tienen, encuentra la
    entidad/municipio/clase del catalogo y llena el desplegable. Sin recaptura."""
    Ent = env['pila.entidad']; Mun = env['pila.municipio']; Cla = env['pila.arl.clase']
    for ct in env['hr.contract'].search([]):
        vals = {}
        pairs = [
            ('pila_eps_code', 'pila_eps_id', Ent, 'eps'),
            ('pila_afp_code', 'pila_afp_id', Ent, 'afp'),
            ('pila_arl_code', 'pila_arl_id', Ent, 'arl'),
            ('pila_ccf_code', 'pila_ccf_id', Ent, 'ccf'),
        ]
        for char_f, m2o, Model, tipo in pairs:
            code = (getattr(ct, char_f, '') or '').strip()
            if code:
                rec = Model.search([('tipo', '=', tipo), ('code', '=', code)], limit=1)
                if rec:
                    vals[m2o] = rec.id
        muni = (getattr(ct, 'pila_municipio_code', '') or '').strip()
        if muni:
            rec = Mun.search([('code', '=', muni)], limit=1)
            if rec:
                vals['pila_municipio_id'] = rec.id
        cla = (getattr(ct, 'pila_arl_class', '') or '').strip()
        if cla:
            rec = Cla.search([('code', '=', cla)], limit=1)
            if rec:
                vals['pila_arl_clase_id'] = rec.id
        if vals:
            ct.write(vals)  # sincroniza los codigos (idempotente: mismo valor)
