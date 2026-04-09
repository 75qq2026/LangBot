from __future__ import annotations

from importlib import import_module


def get_customer_service_module():
    return import_module('langbot.pkg.api.http.service.customer')


def test_build_customer_updates_merges_profile_fields():
    customer_service_module = get_customer_service_module()
    service = customer_service_module.CustomerService(ap=None)

    current_customer = {
        'conversation_count': 2,
        'tags': ['vip'],
        'profile_data': {
            'name': 'Old Name',
            'notes': 'legacy note',
        },
    }
    extracted_profile = {
        'name': 'Alice',
        'phone': '138 0013 8000',
        'requirements': 'Need a two-bedroom apartment near subway',
        'notes': 'Budget around 8k',
        'tags': ['vip', 'rental'],
        'summary': 'Interested in renting an apartment',
    }

    updates = service._build_customer_updates(
        current_customer=current_customer,
        extracted_profile=extracted_profile,
        increment_conversation_count=True,
        set_extracted_at=True,
    )

    assert updates['name'] == 'Alice'
    assert updates['phone'] == '13800138000'
    assert updates['requirements'] == 'Need a two-bedroom apartment near subway'
    assert updates['notes'] == 'Budget around 8k'
    assert updates['latest_summary'] == 'Interested in renting an apartment'
    assert updates['conversation_count'] == 3
    assert updates['tags'] == ['vip', 'rental']
    assert updates['profile_data']['name'] == 'Alice'
    assert updates['profile_data']['phone'] == '13800138000'
    assert updates['profile_data']['summary'] == 'Interested in renting an apartment'
    assert 'last_extracted_at' in updates


def test_infer_profile_from_text_extracts_contact_info():
    customer_service_module = get_customer_service_module()
    service = customer_service_module.CustomerService(ap=None)

    inferred = service._infer_profile_from_text(
        '你好，我叫王磊，电话是 13800138000，邮箱是 wl@example.com，我想租一个离地铁近的两居室。'
    )

    assert inferred['name'] == '王磊'
    assert inferred['phone'] == '13800138000'
    assert inferred['email'] == 'wl@example.com'
    assert '两居室' in inferred['requirements']
