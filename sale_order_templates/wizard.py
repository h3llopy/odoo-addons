# -*- coding: utf8 -*-
#
#    Copyright (C) 2016 NDP Systèmes (<http://www.ndp-systemes.fr>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from openerp import models, fields, api, _


class SaleOrderTemplateGeneration(models.TransientModel):
    _name = 'sale.order.template.generation'
    _description = "Génération d'une commande de vente à partir d'un template"

    template_id = fields.Many2one('sale.order', string="Sale order template")
    partner_ids = fields.Many2many('res.partner', string="Partners", required=True, domain=[('customer', '=', True)],
                                   context={'default_customer': True})

    @api.multi
    def generate_sale_orders(self):
        self.ensure_one()
        new_sale_orders = []
        for partner in self.partner_ids:
            vals = self.template_id.get_default_values_generated_order(partner)
            addr = partner.address_get(['delivery', 'invoice'])
            values = {
                'pricelist_id': partner.property_product_pricelist and partner.property_product_pricelist.id or False,
                'payment_term_id': partner.property_payment_term_id and partner.property_payment_term_id.id or False,
                'partner_invoice_id': addr['invoice'],
                'partner_shipping_id': addr['delivery'],
                'note': self.with_context(lang=partner.lang).env.user.company_id.sale_note,
            }
            if partner.user_id:
                values['user_id'] = self.partner_id.user_id.id
            if partner.team_id:
                values['team_id'] = self.partner_id.team_id.id
            vals.update(values)
            new_sale_order = self.template_id.copy(vals)
            new_sale_orders += [new_sale_order]
        if len(new_sale_orders) == 1:
            return {
                'name': _("Sale order generated from template %s") % self.template_id.display_name,
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'sale.order',
                'context': self.env.context,
                'res_id': new_sale_order.id,
                'flags': {'form': {'options': {'mode': 'edit'}}}
            }
        if len(new_sale_orders) > 1:
            return {
                'name': _("Sale orders generated from template %s") % self.template_id.display_name,
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'sale.order',
                'context': self.env.context,
                'domain': [('id', 'in', [order.id for order in new_sale_orders])]
            }
