# -*- coding: utf8 -*-
#
#    Copyright (C) 2018 NDP Systèmes (<http://www.ndp-systemes.fr>).
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

from openerp import exceptions, _


class NotReschedulableTiaTaskError(exceptions.UserError):

    def __init__(self, task_id):
        self.task_id = task_id
        super(NotReschedulableTiaTaskError, self).__init__(_(u"Impossible to schedule task %s, because it is already "
                                                             u"taken into account") % self.task_id.display_name)


class ReDisplayTaskForbidden(exceptions.UserError):

    def __init__(self, task_id):
        self.task_id = task_id
        super(ReDisplayTaskForbidden, self).__init__(_(u"Impossible to display %s, please display first task %s")
                                                     % (self.task_id.display_name,
                                                        self.task_id.hidden_from_task_id.display_name))


class StartDateNotWorkingPeriod(exceptions.ValidationError):

    def __init__(self, task_id, date):
        self.task_id = task_id
        self.date = date
        super(StartDateNotWorkingPeriod, self).__init__(_(u"Task %s: impossible to set start date in a not working "
                                                          u"period (%s)") % (self.task_id.display_name, date))


class EndDateNotWorkingPeriod(exceptions.ValidationError):

    def __init__(self, task_id, date):
        self.task_id = task_id
        self.date = date
        super(EndDateNotWorkingPeriod, self).__init__(_(u"Task %s: impossible to set end date in a not working "
                                                        u"period (%s)") % (self.task_id.display_name, date))
