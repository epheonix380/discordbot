from storage.models import ListOfChoices, Item, Member
from storage.serializers import ItemSerializer
from asgiref.sync import sync_to_async

@sync_to_async
def getRecentChoice(uid):
    qs = ListOfChoices.objects.filter(member__member_id=uid).order_by('-last_used')
    if (qs.count() > 0):
        return ItemSerializer(qs[0].item_set.all(), many=True).data
    else:
        return None

@sync_to_async
def setRecentChoice(uid, list):
    member, member_created = Member.objects.get_or_create(member_id=uid)
    list_of_choices = ListOfChoices(member=member)
    list_of_choices.save()
    for choice in list:
        item = Item(list=list_of_choices, name=str(choice))
        item.save()
    return True
