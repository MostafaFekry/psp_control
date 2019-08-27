frappe.listview_settings['Collect Production Item'] = {
	add_fields: ["item_name", "status", "quantity", "total_cost",
		"per_reserved", "per_transferred", "expected_delivery_date"],
	filters: [["status", "!=", "Cancelled"]],
	get_indicator: function(doc) {
		if(doc.status==="Submitted") {
			return [__("Not Started"), "Light Blue", "status,=,Submitted"];
		} else {
			return [__(doc.status), {
				"Draft": "red",
				"Stopped": "red",
				"On Hold": "grey",
				"Not Started": "lightblue",
				"In Process": "orange",
				"Waiting for Approval": "blue",
				"To BOM": "purple",
				"To Work Order": "purple",
				"To Finish Good": "purple",
				"Completed": "green",
				"Cancelled": "darkgrey"
			}[doc.status], "status,=," + doc.status];
		}
	}
};