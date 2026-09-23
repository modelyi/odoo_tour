account_analytic_account	account_analytic_account_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
account_asset_category	account_asset_category_account_asset_id_fkey	FOREIGN KEY (account_asset_id) REFERENCES account_account(id) ON DELETE RESTRICT
account_asset_category	account_asset_category_account_depreciation_expense_id_fkey	FOREIGN KEY (account_depreciation_expense_id) REFERENCES account_account(id) ON DELETE RESTRICT
account_asset_category	account_asset_category_account_depreciation_id_fkey	FOREIGN KEY (account_depreciation_id) REFERENCES account_account(id) ON DELETE RESTRICT
account_asset_category	account_asset_category_account_disposal_id_fkey	FOREIGN KEY (account_disposal_id) REFERENCES account_account(id) ON DELETE SET NULL
account_asset_category	account_asset_category_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
account_bank_statement	account_bank_statement_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
account_bank_statement_line	account_bank_statement_line_account_id_fkey	FOREIGN KEY (account_id) REFERENCES account_account(id) ON DELETE SET NULL
account_bank_statement_line	account_bank_statement_line_move_id_fkey	FOREIGN KEY (move_id) REFERENCES account_move(id) ON DELETE CASCADE
account_bank_statement_line	account_bank_statement_line_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
account_bulk_payment	account_bulk_payment_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
account_fiscal_position	account_fiscal_position_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
account_followup	account_followup_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
account_journal	account_journal_default_account_id_fkey	FOREIGN KEY (default_account_id) REFERENCES account_account(id) ON DELETE RESTRICT
account_journal	account_journal_loss_account_id_fkey	FOREIGN KEY (loss_account_id) REFERENCES account_account(id) ON DELETE SET NULL
account_journal	account_journal_non_deductible_account_id_fkey	FOREIGN KEY (non_deductible_account_id) REFERENCES account_account(id) ON DELETE SET NULL
account_journal	account_journal_profit_account_id_fkey	FOREIGN KEY (profit_account_id) REFERENCES account_account(id) ON DELETE SET NULL
account_journal	account_journal_suspense_account_id_fkey	FOREIGN KEY (suspense_account_id) REFERENCES account_account(id) ON DELETE RESTRICT
account_journal	account_journal_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
account_move	account_move_team_id_fkey	FOREIGN KEY (team_id) REFERENCES crm_team(id) ON DELETE SET NULL
account_move	account_move_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
account_move	account_move_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
account_move	account_move_invoice_user_id_fkey	FOREIGN KEY (invoice_user_id) REFERENCES res_users(id) ON DELETE SET NULL
account_move	account_move_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
account_move_line	account_move_line_account_id_fkey	FOREIGN KEY (account_id) REFERENCES account_account(id) ON DELETE RESTRICT
account_move_line	account_move_line_move_id_fkey	FOREIGN KEY (move_id) REFERENCES account_move(id) ON DELETE CASCADE
account_move_line	account_move_line_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
account_partial_reconcile	account_partial_reconcile_exchange_move_id_fkey	FOREIGN KEY (exchange_move_id) REFERENCES account_move(id) ON DELETE SET NULL
account_partial_reconcile	account_partial_reconcile_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
account_payment	account_payment_destination_account_id_fkey	FOREIGN KEY (destination_account_id) REFERENCES account_account(id) ON DELETE SET NULL
account_payment	account_payment_outstanding_account_id_fkey	FOREIGN KEY (outstanding_account_id) REFERENCES account_account(id) ON DELETE SET NULL
account_payment	account_payment_move_id_fkey	FOREIGN KEY (move_id) REFERENCES account_move(id) ON DELETE SET NULL
account_payment	account_payment_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
account_payment_method_line	account_payment_method_line_payment_account_id_fkey	FOREIGN KEY (payment_account_id) REFERENCES account_account(id) ON DELETE RESTRICT
account_payment_term	account_payment_term_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
account_reconcile_model	account_reconcile_model_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
account_recurring_invoice	account_recurring_invoice_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
account_tax	account_tax_cash_basis_transition_account_id_fkey	FOREIGN KEY (cash_basis_transition_account_id) REFERENCES account_account(id) ON DELETE SET NULL
account_tax	account_tax_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
account_tax_group	account_tax_group_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
account_tax_repartition_line	account_tax_repartition_line_account_id_fkey	FOREIGN KEY (account_id) REFERENCES account_account(id) ON DELETE SET NULL
account_tax_repartition_line	account_tax_repartition_line_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
crm_iap_lead_mining_request	crm_iap_lead_mining_request_team_id_fkey	FOREIGN KEY (team_id) REFERENCES crm_team(id) ON DELETE SET NULL
crm_iap_lead_mining_request	crm_iap_lead_mining_request_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
crm_iap_lead_mining_request	crm_iap_lead_mining_request_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE SET NULL
crm_iap_lead_mining_request	crm_iap_lead_mining_request_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
crm_lead	crm_lead_team_id_fkey	FOREIGN KEY (team_id) REFERENCES crm_team(id) ON DELETE SET NULL
crm_lead	crm_lead_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
crm_lead	crm_lead_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
crm_lead	crm_lead_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE SET NULL
crm_lead	crm_lead_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
crm_lead	crm_lead_plan_id_fkey	FOREIGN KEY (plan_id) REFERENCES tour_plan(id) ON DELETE SET NULL
crm_team	crm_team_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
crm_team	crm_team_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE SET NULL
crm_team	crm_team_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
delivery_carrier	delivery_carrier_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
fleet_vehicle	fleet_vehicle_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
fleet_vehicle	fleet_vehicle_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
fleet_vehicle	fleet_vehicle_manager_id_fkey	FOREIGN KEY (manager_id) REFERENCES res_users(id) ON DELETE SET NULL
fleet_vehicle	fleet_vehicle_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
hr_department	hr_department_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
hr_employee	hr_employee_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
hr_employee	hr_employee_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
hr_employee	hr_employee_expense_manager_id_fkey	FOREIGN KEY (expense_manager_id) REFERENCES res_users(id) ON DELETE SET NULL
hr_employee	hr_employee_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE RESTRICT
hr_employee	hr_employee_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
hr_expense	hr_expense_account_id_fkey	FOREIGN KEY (account_id) REFERENCES account_account(id) ON DELETE SET NULL
hr_expense	hr_expense_account_move_id_fkey	FOREIGN KEY (account_move_id) REFERENCES account_move(id) ON DELETE SET NULL
hr_expense	hr_expense_existing_bill_id_fkey	FOREIGN KEY (existing_bill_id) REFERENCES account_move(id) ON DELETE SET NULL
hr_expense	hr_expense_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
hr_expense	hr_expense_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
hr_expense	hr_expense_manager_id_fkey	FOREIGN KEY (manager_id) REFERENCES res_users(id) ON DELETE SET NULL
hr_expense	hr_expense_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
hr_job	hr_job_department_id_fkey	FOREIGN KEY (department_id) REFERENCES hr_department(id) ON DELETE SET NULL
hr_job	hr_job_recruiter_id_fkey	FOREIGN KEY (recruiter_id) REFERENCES hr_employee(id) ON DELETE SET NULL
hr_job	hr_job_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
hr_job	hr_job_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
hr_job	hr_job_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
hr_version	hr_version_department_id_fkey	FOREIGN KEY (department_id) REFERENCES hr_department(id) ON DELETE SET NULL
hr_version	hr_version_employee_id_fkey	FOREIGN KEY (employee_id) REFERENCES hr_employee(id) ON DELETE SET NULL
hr_version	hr_version_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
hr_version	hr_version_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
hr_version	hr_version_hr_responsible_id_fkey	FOREIGN KEY (hr_responsible_id) REFERENCES res_users(id) ON DELETE RESTRICT
hr_version	hr_version_last_modified_uid_fkey	FOREIGN KEY (last_modified_uid) REFERENCES res_users(id) ON DELETE RESTRICT
hr_version	hr_version_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
hr_work_location	hr_work_location_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
ir_attachment	ir_attachment_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
ir_mail_server	ir_mail_server_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
ir_mail_server	ir_mail_server_owner_user_id_fkey	FOREIGN KEY (owner_user_id) REFERENCES res_users(id) ON DELETE SET NULL
ir_mail_server	ir_mail_server_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
mail_activity_type	mail_activity_type_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
mail_activity_type	mail_activity_type_default_user_id_fkey	FOREIGN KEY (default_user_id) REFERENCES res_users(id) ON DELETE SET NULL
mail_activity_type	mail_activity_type_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
mail_message	mail_message_record_company_id_fkey	FOREIGN KEY (record_company_id) REFERENCES res_company(id) ON DELETE SET NULL
mail_template	mail_template_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
mail_template	mail_template_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE SET NULL
mail_template	mail_template_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
payment_provider	payment_provider_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
payment_token	payment_token_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
payment_transaction	payment_transaction_payment_id_fkey	FOREIGN KEY (payment_id) REFERENCES account_payment(id) ON DELETE SET NULL
payment_transaction	payment_transaction_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
product_combo	product_combo_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
product_combo_item	product_combo_item_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
product_pricelist	product_pricelist_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
product_template	product_template_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
project_project	project_project_account_id_fkey	FOREIGN KEY (account_id) REFERENCES account_analytic_account(id) ON DELETE SET NULL
project_project	project_project_x_plan2_id_fkey	FOREIGN KEY (x_plan2_id) REFERENCES account_analytic_account(id) ON DELETE RESTRICT
project_project	project_project_x_plan3_id_fkey	FOREIGN KEY (x_plan3_id) REFERENCES account_analytic_account(id) ON DELETE RESTRICT
project_project	project_project_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
project_project	project_project_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
project_project	project_project_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE SET NULL
project_project	project_project_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
project_project	project_project_tour_plan_id_fkey	FOREIGN KEY (tour_plan_id) REFERENCES tour_plan(id) ON DELETE RESTRICT
project_project_stage	project_project_stage_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
project_task	project_task_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
project_task	project_task_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
project_task	project_task_force_user_id_fkey	FOREIGN KEY (force_user_id) REFERENCES res_users(id) ON DELETE SET NULL
project_task	project_task_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
project_task_type	project_task_type_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
project_task_type	project_task_type_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE SET NULL
project_task_type	project_task_type_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
project_update	project_update_project_id_fkey	FOREIGN KEY (project_id) REFERENCES project_project(id) ON DELETE RESTRICT
project_update	project_update_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
project_update	project_update_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE RESTRICT
project_update	project_update_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
purchase_order	purchase_order_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
purchase_order	purchase_order_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
purchase_order	purchase_order_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE SET NULL
purchase_order	purchase_order_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
purchase_order_line	purchase_order_line_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
res_company	res_company_account_cash_basis_base_account_id_fkey	FOREIGN KEY (account_cash_basis_base_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_account_default_pos_receivable_account_id_fkey	FOREIGN KEY (account_default_pos_receivable_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_account_discount_expense_allocation_id_fkey	FOREIGN KEY (account_discount_expense_allocation_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_account_discount_income_allocation_id_fkey	FOREIGN KEY (account_discount_income_allocation_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_account_journal_early_pay_discount_gain_accoun_fkey	FOREIGN KEY (account_journal_early_pay_discount_gain_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_account_journal_early_pay_discount_loss_accoun_fkey	FOREIGN KEY (account_journal_early_pay_discount_loss_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_account_journal_suspense_account_id_fkey	FOREIGN KEY (account_journal_suspense_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_default_cash_difference_expense_account_id_fkey	FOREIGN KEY (default_cash_difference_expense_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_default_cash_difference_income_account_id_fkey	FOREIGN KEY (default_cash_difference_income_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_downpayment_account_id_fkey	FOREIGN KEY (downpayment_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_expense_accrual_account_id_fkey	FOREIGN KEY (expense_accrual_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_expense_currency_exchange_account_id_fkey	FOREIGN KEY (expense_currency_exchange_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_fx_reval_gain_account_id_fkey	FOREIGN KEY (fx_reval_gain_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_fx_reval_loss_account_id_fkey	FOREIGN KEY (fx_reval_loss_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_income_currency_exchange_account_id_fkey	FOREIGN KEY (income_currency_exchange_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_price_difference_account_id_fkey	FOREIGN KEY (price_difference_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_revenue_accrual_account_id_fkey	FOREIGN KEY (revenue_accrual_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_company	res_company_transfer_account_id_fkey	FOREIGN KEY (transfer_account_id) REFERENCES account_account(id) ON DELETE SET NULL
res_partner	res_partner_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
res_partner	res_partner_buyer_id_fkey	FOREIGN KEY (buyer_id) REFERENCES res_users(id) ON DELETE SET NULL
res_partner	res_partner_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
res_partner	res_partner_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE SET NULL
res_partner	res_partner_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
res_partner_bank	res_partner_bank_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
resource_calendar	resource_calendar_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
resource_resource	resource_resource_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
resource_resource	resource_resource_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
resource_resource	resource_resource_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE SET NULL
resource_resource	resource_resource_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
sale_order	sale_order_team_id_fkey	FOREIGN KEY (team_id) REFERENCES crm_team(id) ON DELETE SET NULL
sale_order	sale_order_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
sale_order	sale_order_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
sale_order	sale_order_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE SET NULL
sale_order	sale_order_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
sale_order_line	sale_order_line_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
sale_order_line	sale_order_line_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
sale_order_line	sale_order_line_salesman_id_fkey	FOREIGN KEY (salesman_id) REFERENCES res_users(id) ON DELETE SET NULL
sale_order_line	sale_order_line_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
sale_order_line	sale_order_line_reg_id_fkey	FOREIGN KEY (reg_id) REFERENCES tour_plan_reg(id) ON DELETE SET NULL
tour_account_period	tour_account_period_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
tour_departure	tour_departure_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
tour_driver	tour_driver_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
tour_guide	tour_guide_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
tour_guide	tour_guide_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
tour_guide	tour_guide_portal_user_id_fkey	FOREIGN KEY (portal_user_id) REFERENCES res_users(id) ON DELETE SET NULL
tour_guide	tour_guide_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
tour_guide_loan	tour_guide_loan_account_id_fkey	FOREIGN KEY (account_id) REFERENCES account_account(id) ON DELETE SET NULL
tour_guide_loan	tour_guide_loan_move_id_fkey	FOREIGN KEY (move_id) REFERENCES account_move(id) ON DELETE RESTRICT
tour_guide_loan	tour_guide_loan_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
tour_guide_loan	tour_guide_loan_applicant_id_fkey	FOREIGN KEY (applicant_id) REFERENCES res_users(id) ON DELETE RESTRICT
tour_guide_loan	tour_guide_loan_approver_id_fkey	FOREIGN KEY (approver_id) REFERENCES res_users(id) ON DELETE SET NULL
tour_guide_loan	tour_guide_loan_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
tour_guide_loan	tour_guide_loan_disburser_id_fkey	FOREIGN KEY (disburser_id) REFERENCES res_users(id) ON DELETE SET NULL
tour_guide_loan	tour_guide_loan_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
tour_line	tour_line_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
tour_line	tour_line_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
tour_line	tour_line_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE SET NULL
tour_line	tour_line_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
tour_plan	tour_plan_analytic_account_id_fkey	FOREIGN KEY (analytic_account_id) REFERENCES account_analytic_account(id) ON DELETE SET NULL
tour_plan	tour_plan_cost_bill_id_fkey	FOREIGN KEY (cost_bill_id) REFERENCES account_move(id) ON DELETE RESTRICT
tour_plan	tour_plan_income_move_id_fkey	FOREIGN KEY (income_move_id) REFERENCES account_move(id) ON DELETE RESTRICT
tour_plan	tour_plan_vat_deduct_move_id_fkey	FOREIGN KEY (vat_deduct_move_id) REFERENCES account_move(id) ON DELETE RESTRICT
tour_plan	tour_plan_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
tour_plan	tour_plan_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
tour_plan	tour_plan_finance_audit_uid_fkey	FOREIGN KEY (finance_audit_uid) REFERENCES res_users(id) ON DELETE SET NULL
tour_plan	tour_plan_in_user_id_fkey	FOREIGN KEY (in_user_id) REFERENCES res_users(id) ON DELETE SET NULL
tour_plan	tour_plan_operation_audit_uid_fkey	FOREIGN KEY (operation_audit_uid) REFERENCES res_users(id) ON DELETE SET NULL
tour_plan	tour_plan_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE SET NULL
tour_plan	tour_plan_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
tour_plan_reg	tour_plan_reg_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
tour_plan_reg	tour_plan_reg_in_user_id_fkey	FOREIGN KEY (in_user_id) REFERENCES res_users(id) ON DELETE SET NULL
tour_plan_reg	tour_plan_reg_op_user_id_fkey	FOREIGN KEY (op_user_id) REFERENCES res_users(id) ON DELETE SET NULL
tour_plan_reg	tour_plan_reg_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
tour_plan_reg	tour_plan_reg_first_plan_id_fkey	FOREIGN KEY (first_plan_id) REFERENCES tour_plan(id) ON DELETE RESTRICT
tour_plan_reg	tour_plan_reg_plan_id_fkey	FOREIGN KEY (plan_id) REFERENCES tour_plan(id) ON DELETE RESTRICT
tour_plan_reg	tour_plan_reg_plan_id_main_reg_fkey	FOREIGN KEY (plan_id_main_reg) REFERENCES tour_plan(id) ON DELETE SET NULL
tour_supplier	tour_supplier_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE SET NULL
utm_campaign	utm_campaign_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
utm_campaign	utm_campaign_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE RESTRICT
utm_campaign	utm_campaign_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
website	website_crm_default_team_id_fkey	FOREIGN KEY (crm_default_team_id) REFERENCES crm_team(id) ON DELETE SET NULL
website	website_salesteam_id_fkey	FOREIGN KEY (salesteam_id) REFERENCES crm_team(id) ON DELETE SET NULL
website	website_company_id_fkey	FOREIGN KEY (company_id) REFERENCES res_company(id) ON DELETE RESTRICT
website	website_create_uid_fkey	FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
website	website_crm_default_user_id_fkey	FOREIGN KEY (crm_default_user_id) REFERENCES res_users(id) ON DELETE SET NULL
website	website_salesperson_id_fkey	FOREIGN KEY (salesperson_id) REFERENCES res_users(id) ON DELETE SET NULL
website	website_user_id_fkey	FOREIGN KEY (user_id) REFERENCES res_users(id) ON DELETE RESTRICT
website	website_write_uid_fkey	FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
