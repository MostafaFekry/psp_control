from __future__ import unicode_literals
from frappe import _

def get_data():
	return {
		'fieldname': 'collect_production_item',
		'transactions': [
			{
				'label': _('Purchasing'),
				'items': ['Material Request']
			},
			{
				'label': _('Manufacturing'),
				'items': ['Stock Entry','BOM','Work Order']
			}
		]
	}