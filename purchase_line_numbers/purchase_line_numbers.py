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


class ReceptionByOrderPurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.multi
    def renumerate_lines(self):
        dict_line_no = {}
        max_number = 0
        for rec in self:
            number = 10
            for line in rec.order_line.sort_lines_to_renumerate():
                dict_line_no[line] = number
                max_number = max(max_number, number)
                number += 10
        nb_letters = str(len(str(max_number)))
        no_format = "%0" + nb_letters + "d"
        for rec in self:
            for line in rec.order_line:
                line.line_no = no_format % dict_line_no[line]

    @api.multi
    def do_merge(self):
        result = super(ReceptionByOrderPurchaseOrder, self).do_merge()
        if len(result.keys()) == 1 and isinstance(result.keys()[0], int):
            children_po = self.env['purchase.order'].browse(result.keys()[0])
            children_po.renumerate_lines()
        return result


class ReceptionByOrderPurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    line_no = fields.Char("Line No.")

    @api.multi
    def sort_lines_to_renumerate(self):
        return self

    @api.multi
    def name_get(self):
        if self.env.context.get('display_line_no'):
            return [(rec.id, u"%s - %s" % (rec.order_id.name, rec.line_no)) for rec in self]
        return super(ReceptionByOrderPurchaseOrderLine, self).name_get()

    @api.model
    def create(self, vals):
        if not vals.get('line_no', False):
            order = self.env['purchase.order'].browse(vals['order_id'])
            list_line_no = []
            for line in order.order_line:
                try:
                    list_line_no.append(int(line.line_no))
                except ValueError:
                    pass
            theo_value = 10 * (1 + len(order.order_line))
            maximum = list_line_no and max(list_line_no) or 0
            if maximum >= theo_value or theo_value in list_line_no:
                theo_value = maximum + 10
            vals['line_no'] = "%03d" % theo_value
        return super(ReceptionByOrderPurchaseOrderLine, self).create(vals)
