"""Exact current ticket choices; shared180/group25 validator owns the catalog."""
import hashlib
from els_server.domain.tenebros_rules import catalog,template_info,supports,validate as shadow_validate
from els_server.game_data import client_data


def options(template,slot,ticket):
    if type(template) is not int or type(slot) is not int or type(ticket) is not int:
        raise ValueError('Tenebros select rule identity')
    if not supports(template) or slot not in (0,1,2) or str(ticket) not in catalog()['tickets']:
        raise ValueError('Outside verified Tenebros select scope')
    if ticket in (718665,718666):
        matches=[row['options'] for row in catalog()['ticket_selection']
                 if row['slot']==slot and template in row['templates'] and ticket in row['tickets']]
        if len(matches)!=1:raise ValueError('No unique ticket-specific Tenebros choices')
        return list(matches[0])
    return list(template_info(template)['selection'][slot])


def selection(target,ticket,slot,option):
    if (target is None or not supports(target['template'])
        or target['group']!=1 or target['count']!=1 or target.get('sealed')
        or target.get('identified') is False or target.get('enhancement',0)<0):
        raise ValueError('Owned identified bag Tenebros equipment required')
    if (ticket is None or str(ticket['template']) not in catalog()['tickets'] or ticket['group']!=4
        or ticket['metadata']!=catalog()['tickets'][str(ticket['template'])]['metadata']
        or type(ticket['count']) is not int or ticket['count']<1 or ticket.get('sealed')
        or ticket.get('identified') is False or ticket['uid']==target['uid']):
        raise ValueError('Owned exact select-ticket instance required')
    for item,expected in ((target,template_info(target['template'])['record_sha256']),
                          (ticket,catalog()['tickets'][str(ticket['template'])]['record_sha256'])):
        if hashlib.sha256(client_data().item(item['template'])['record']).hexdigest()!=expected:
            raise ValueError('Tenebros select source record changed')
    previous=target.get('option_groups',{})
    values=shadow_validate(target['template'],previous.get('25',[]))
    if type(option) is not int or option not in options(target['template'],slot,ticket['template']):
        raise ValueError('Option is outside exact slot/target/ticket list')
    # The support-ticket values are finite IDs from the current table, not a
    # generic max-value/reroll policy. Other shadow slots are byte-value retained.
    updated=list(values);updated[slot]=option
    shadow_validate(target['template'],updated)
    return {**previous,'25':updated}
