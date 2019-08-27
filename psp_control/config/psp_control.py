from __future__ import unicode_literals
import frappe
from frappe import _

def get_data():
	return [
		{
			"label": _("PSP"),
			"icon": "fa fa-star",
			"items": [
				{
					"type": "doctype",
					"name": "Collect Production Item",
					"description": _("Collect Production Item."),
					"onboard": 1,
				},
			]
		},
		{
			"label": _("Settings"),
			"icon": "fa fa-cog",
			"items": [
				{
					"type": "doctype",
					"name": "PSP Settings",
				},
			]
		},
	]

	