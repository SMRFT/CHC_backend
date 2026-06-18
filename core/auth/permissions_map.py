PAGE_MAPPING = {

    # Admin URLs
    r'^/_b_a_c_k_e_n_d/CHC/get_investigation_checklists/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/update_investigation_checklist/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/get_approval_dashboard/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/get_approval_report/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/registration/?(\?.*)?$':'CHC-API-ADM',
    '/_b_a_c_k_e_n_d/CHC/get_employee_types/':'CHC-API-ADM',
    '/_b_a_c_k_e_n_d/CHC/get_next_offsite_barcode/':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/companies/?(\?.*)?$':'CHC-API-ADM',
    '/_b_a_c_k_e_n_d/CHC/companies/':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/get_packages/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/get_test_details/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/get_unregistered_employees/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/chc_empregisterandbilling/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/get_offsite_billings/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/billing/patients/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/samples/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/samples/transferred/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/batch/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/get_all_employees/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/get_investigations/?(\?.*)?$':'CHC-API-ADM',
    '/_b_a_c_k_e_n_d/CHC/approve_investigation/.*/':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/save_investigation/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/get_all_registered_employees/?(\?.*)?$':'CHC-API-ADM',
    '/_b_a_c_k_e_n_d/CHC/get_core_test/':'CHC-API-ADM',
    '/_b_a_c_k_e_n_d/CHC/dynamic_fields/':'CHC-API-ADM',
    '/_b_a_c_k_e_n_d/CHC/create_package/':'CHC-API-ADM',
    '/_b_a_c_k_e_n_d/CHC/addon_investigations/':'CHC-API-ADM',
    '/_b_a_c_k_e_n_d/CHC/dynamic_fields/next-id/':'CHC-API-ADM',
    '/_b_a_c_k_e_n_d/CHC/addon_investigations/next-id/':'CHC-API-ADM',

    r'^/_b_a_c_k_e_n_d/CHC/get_credit_billings/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/mark_as_paid/?(\?.*)?$':'CHC-API-ADM',
    r'^/_b_a_c_k_e_n_d/CHC/payment_report/?(\?.*)?$':'CHC-API-ADM',
    
    # Company
    r'^/_b_a_c_k_e_n_d/CHC/investigations/?(\?.*)?$':'CHC-API-CMP',
    r'^/_b_a_c_k_e_n_d/CHC/employees/?(\?.*)?$':'CHC-API-CMP',
    r'^/_b_a_c_k_e_n_d/CHC/billings/?(\?.*)?$':'CHC-API-CMP',
    r'^/_b_a_c_k_e_n_d/CHC/create_package/?(\?.*)?$':'CHC-API-CMP',

}


PAGE_ACTION_MAPPING = {
    'xxx': {
        'DELETE':'RWD',
    },
}

GEN_ACTION_MAPPING = {
    'POST': 'RW',
    'PUT': 'RW',
    'PATCH': 'RW',
    'DELETE': 'RW',
    'GET': 'R',
}


