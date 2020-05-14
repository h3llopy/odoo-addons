# -*- coding: utf8 -*-
#
# Copyright (C) 2015 NDP Systèmes (<http://www.ndp-systemes.fr>).
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

from openerp import models, api, fields


class QueueJob(models.Model):
    _inherit = "queue.job"

    date_requeued = fields.Datetime(string=u"Requeued at", track_visibility='onchange')

    @api.multi
    def set_to_done(self):
        """Sets to done the given jobs if they are not running."""
        for job in self:
            if job.state != 'Started':
                job.button_done()

    @api.multi
    def requeue(self):
        result = super(QueueJob, self).requeue()
        self.write({'date_requeued': fields.Datetime.now()})
        return result

    @api.model
    def create(self, vals):
        # The creation message is useless
        return super(QueueJob, self.with_context(mail_notrack=True, mail_create_nolog=True)).create(vals)

    @api.multi
    def write(self, vals):
        # The fail message is useless
        return super(QueueJob, self.with_context(mail_notrack=vals.get('state') == 'failed')).write(vals)