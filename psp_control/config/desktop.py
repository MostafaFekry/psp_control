# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe import _

def get_data():
	return [
		{
			"module_name": "PSP Control",
			"category": "Modules",
			"label": _("PSP Control"),
			"color": "#bdc3c7",
			"reverse": 1,
			"icon": "octicon octicon-tools",
			"type": "module",
			"description": "Control item manufacture and tender."
		}
	]
