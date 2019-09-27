from __future__ import unicode_literals
from frappe import _

def get_data():
	return {
		'fieldname': 'collect_production_item',
		'transactions': [
			
			{
				'label': _('Stock'),
				'items': ['Material Request','Purchase Receipt','Stock Entry']
			},
			{
				'label': _('Purchasing'),
				'items': ['Request for Quotation','Supplier Quotation','Purchase Order']
			},
			{
				'label': _('Manufacturing'),
				'items': ['BOM','Work Order']
			}
		]
	}