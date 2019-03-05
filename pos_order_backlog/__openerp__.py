# -*- coding: utf8 -*-
#
# Copyright (C) 2017 NDP Systèmes (<http://www.ndp-systemes.fr>).
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

{
    'name': 'Point Of Sale - Backlog',
    'author': 'NDP Systèmes',
    'maintainer': 'NDP Systèmes',
    'version': '1.0',
    'category': 'Point of Sale',
    'depends': ['point_of_sale'],
    'license': 'AGPL-3',
    'description': """
Restaurant - Allergen Management
================================

This module adds a new menu *POS Order Lines* in the *Point Of Sale* application.""",
    'website': 'http://www.ndp-systemes.fr',
    'data': [
        'pos_order_backlog.xml',
    ],
    'demo': [],
    'test': [],
    'installable': True,
    'auto_install': False,
    'license': 'AGPL-3',
    'application': False,
}