# -*- coding: utf8 -*-
#
#    Copyright (C) 2015 NDP Systèmes (<http://www.ndp-systemes.fr>).
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

import re

from openerp import models, api
from openerp.osv import expression
from openerp.tools import float_round


class ProductLabelProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not args:
            args = []
        if name:
            positive_operators = ['=', 'ilike', '=ilike', 'like', '=like']
            products = self.env['product.product']
            if operator in positive_operators:
                products = self.search([('default_code', operator, name)] + args, limit=limit)
                if not products:
                    products = self.search([('ean13', operator, name)] + args, limit=limit)
            if not products and operator not in expression.NEGATIVE_TERM_OPERATORS:
                # Do not merge the 2 next lines into one single search, SQL search performance would be abysmal
                # on a database with thousands of matching products, due to the huge merge+unique needed for the
                # OR operator (and given the fact that the 'name' lookup results come from the ir.translation table
                # Performing a quick memory merge of ids in Python will give much better performance
                products = self.search(args + [('default_code', operator, name)], limit=limit)
                if not limit or len(products) < limit:
                    # we may underrun the limit because of dupes in the results, that's fine
                    limit2 = (limit - len(products)) if limit else False
                    products |= self.search(args + [('name', operator, name),
                                                    ('id', 'not in', products.ids)], limit=limit2)
            elif not products and operator in expression.NEGATIVE_TERM_OPERATORS:
                products = self.search(args + ['&', '|', ('default_code', operator, name), (
                    'default_code', '=', False), ('name', operator, name)], limit=limit)
            if not products and operator in positive_operators:
                ptrn = re.compile(r'(\[(.*?)\])')
                res = ptrn.search(name)
                if res:
                    products = self.search([('default_code', operator, res.group(2))] + args, limit=limit)
        else:
            products = self.search(args, limit=limit)
        result = products.name_get()
        return result


class ProductUomImproved(models.Model):
    _inherit = 'product.uom'

    def _compute_qty_obj(self, cr, uid, from_unit, qty, to_unit, round=True, rounding_method='UP', context=None):
        if from_unit == to_unit:
            res_qty = qty
            if round:
                res_qty = float_round(res_qty, precision_rounding=to_unit.rounding, rounding_method=rounding_method)
            return res_qty
        return super(ProductUomImproved, self).\
            _compute_qty_obj(cr, uid, from_unit, qty, to_unit, round, rounding_method, context)

    def _compute_price(self, cr, uid, from_uom_id, price, to_uom_id=False):
        if from_uom_id == to_uom_id:
            return price
        return super(ProductUomImproved, self). \
            _compute_price(cr, uid, from_uom_id, price, to_uom_id)
